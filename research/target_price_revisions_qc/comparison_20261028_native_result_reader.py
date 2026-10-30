"""Pure source renderer for an optional private in-QC completion diagnostic.

Exact pinned, readable AST-selected evidence/metrics/completion functions only.
All licensed index/chunk rows remain in QC. No native effect or private opener
exists in this renderer. Its caller must separately reserve actual source,
child job, every bounded read/processing claim and outcome observation.
"""
from __future__ import annotations
import ast
from copy import deepcopy
import hashlib
import json
import re

from . import comparison_20261028_completion as completion

PREFIX='research/target_price_revisions_qc/'
PINS={PREFIX+'comparison_20261028_completion.py':'d0489d7c4e1c33207870f4c66e9bf0569145ba1be28f76edd4040685317e5467',
    PREFIX+'extended_evidence.py':'a816b1ddca5a8428f07e9029bc3a7f7db3c5e1a1f50521664992dabf556aa2d7',
    PREFIX+'extended_metrics.py':'a8cfa235c7a54e8f33366570400dbe1bac0a0e900597e94427e5d0c5b7470414',
    PREFIX+'comparison_20261028_algorithm.py':'27c6516b9dfd2d1e71f0ef8fbdb7c371266e36e11bd9e3089e2ce6b76d25aee0',
    PREFIX+'extended_core.py':'706ed5efdcb3999400c5349dc8b5200be1d48c4bb01cbfc7fb080608a679d5da',
    PREFIX+'comparison_20261028.py':'e9b1f513fe453fcd47408171ecbc4342a9321195405c2ce31b7591439f5f44c5',
    PREFIX+'cap_observer.py':'cad8a3306f6b459bc8bf187c8fd8b8bb980c7b1dc0d85465fba11dd318b70c4d',
    PREFIX+'extended_loader.py':'24c752b0859a04d73306e3afddc10d45cc6d3c7b566e2ff17ef160fd90e6e10b'}
SOURCE_PATHS=tuple(PINS)
E_NAMES=frozenset(('STUDY_ID','FREEZE_SHA256','MAX_BYTES','MAX_NODES','MAX_DEPTH','NUMBER','EvidenceError',
    '_fail','digest','JsonNumber','_pairs','canonical','parse_json'))
M_NAMES=frozenset(('CALENDAR_SHA256','INITIAL_NAV','PRECISION','MetricsError','_fail','_exact','_out',
    '_decimal','_stat_text','_calendar','_nav'))
HEADER='''from __future__ import annotations
from AlgorithmImports import *
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from decimal import Decimal, InvalidOperation, localcontext
from fractions import Fraction
import hashlib
import json
import re
import extended_core as core
import comparison_20261028 as comparison
import cap_observer
STUDY = comparison.STUDY_ID
_READER_RUNTIME = None
'''


class NativeReaderBuildRefusal(ValueError):
    """Body-free public framing refusal; not a native/read permission."""


def _fail():raise NativeReaderBuildRefusal('CMP28 native result reader build refused') from None

def _sha(raw):return hashlib.sha256(raw).hexdigest()

def _wire(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')


def _declared(node):
    if isinstance(node,(ast.FunctionDef,ast.ClassDef)):return {node.name}
    if isinstance(node,ast.Assign):return {child.id for target in node.targets for child in ast.walk(target) if isinstance(child,ast.Name)}
    return set()


def _select(raw,names=None):
    nodes=[node for node in ast.parse(raw).body if _declared(node) and (names is None or _declared(node)&names)]
    declared=set().union(*(_declared(node) for node in nodes))
    if names is not None and declared!=set(names):_fail()
    return nodes,declared


class _Names(ast.NodeTransformer):
    def __init__(self,mapping,aliases):self.mapping,self.aliases=mapping,aliases
    def visit_Name(self,node):
        if node.id in self.mapping:return ast.copy_location(ast.Name(id=self.mapping[node.id],ctx=node.ctx),node)
        return node
    def visit_FunctionDef(self,node):
        node.name=self.mapping.get(node.name,node.name);return self.generic_visit(node)
    def visit_ClassDef(self,node):
        node.name=self.mapping.get(node.name,node.name);return self.generic_visit(node)
    def visit_Attribute(self,node):
        if isinstance(node.value,ast.Name) and node.value.id in self.aliases:
            mapping=self.aliases[node.value.id]
            if node.attr not in mapping:_fail()
            return ast.copy_location(ast.Name(id=mapping[node.attr],ctx=node.ctx),node)
        return self.generic_visit(node)


def _render(nodes,mapping,aliases):
    tree=ast.Module(body=deepcopy(nodes),type_ignores=[])
    tree=_Names(mapping,aliases).visit(tree);ast.fix_missing_locations(tree)
    return ast.unparse(tree)+'\n'


NATIVE=r'''
# Pure parse/hash functions keep their exact selected bodies. These wrappers
# add actual native custody around every private invocation, including replay.
def _reader_parse(raw):
    if _READER_RUNTIME is None:raise ValueError('reader runtime unavailable')
    return _READER_RUNTIME._effect('parse',lambda:E_parse_json(raw))
def _reader_hash(raw):
    if _READER_RUNTIME is None:raise ValueError('reader runtime unavailable')
    return _READER_RUNTIME._effect('hash',lambda:C__sha(raw))

class ReaderStopped(BaseException):pass

class Main(QCAlgorithm):
    def initialize(self):
        global _READER_RUNTIME
        self._called=False;self._disabled=False;self._job=None;self._clock_bars=0;self._phase='initialize'
        self._claim_spent=set();self._claims=0;self._reads=0;self._private_bytes=0;self._parse_calls=0;self._hash_calls=0
        self._config_json=READER_CONFIG_JSON;self._config_sha256=READER_CONFIG_SHA256
        frozen=json.loads(self._config_json)
        self._parent_identity=(frozen['binding']['project_id'],frozen['binding']['job_id'],frozen['binding']['config_sha256'],
            frozen['index_key'],frozen['parent_prefix'],frozen['operation_id'])
        self._report={'schema':'tpr-cmp28-native-private-result-reader-v1','status':'callback_not_fired',
            'operation_id':frozen['operation_id'],'root_head':frozen['git_head'],
            'reader_config_sha256':self._config_sha256,'parent_job_id':frozen['binding']['job_id'],
            'actual_child_job_id':None,'phase':'initialize','error_class':None,'claims_same_node_verified':0,
            'private_reads':0,'private_bytes':0,'index_hash_verified':False,'completed_read_replay':False,
            'completion_report':None,'backend_durability_proven':False,'native_origin_authenticated':False,
            'independent_reconciliation_proven':False,'historical_pit_authenticated':False,
            'data_rights_authenticated':False,'source_inputs_admitted':False,'strategy_accepted':False,
            'canonical_admission':False,'accepted_performance':None,'one_of_five_economic_arms':False}
        try:
            self._config_bound()
            if (self.live_mode is not False or self.project_id!=READER_CONFIG['binding']['project_id']
                    or type(self.project_id) is not int or self.get_locked() is not False):
                raise ValueError('reader setup refused')
            _READER_RUNTIME=self
            self.set_time_zone('America/New_York');self.set_start_date(2021,1,4);self.set_end_date(2021,1,4)
            self._clock=self.add_equity('SPY',Resolution.MINUTE,extended_market_hours=True,
                data_normalization_mode=DataNormalizationMode.RAW).symbol
            self.set_benchmark(self._clock)
            self.schedule.on(self.date_rules.every_day(self._clock),self.time_rules.at(16,1),self._audit)
        except KeyboardInterrupt:raise KeyboardInterrupt('CMP28 reader cancelled') from None
        except Exception:self._disabled=True;self._error('setup_refused','Exception')
        except BaseException:raise ReaderStopped('CMP28 reader stopped') from None

    def _error(self,status,kind):self._report.update(status=status,phase=self._phase,error_class=kind)

    def _config_bound(self):
        if (type(READER_CONFIG_JSON) is not str or READER_CONFIG_JSON!=self._config_json
                or type(READER_CONFIG_SHA256) is not str or READER_CONFIG_SHA256!=self._config_sha256
                or hashlib.sha256(READER_CONFIG_JSON.encode('ascii')).hexdigest()!=self._config_sha256
                or type(READER_CONFIG) is not dict
                or json.dumps(READER_CONFIG,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)!=self._config_json):
            raise ValueError('reader frozen configuration drift refused')
        parent=READER_CONFIG['binding']
        if (parent['project_id'],parent['job_id'],parent['config_sha256'],READER_CONFIG['index_key'],
                READER_CONFIG['parent_prefix'],READER_CONFIG['operation_id'])!=self._parent_identity:
            raise ValueError('reader immutable parent identity refused')

    def _bound(self):
        self._config_bound()
        project,job,locked,live=self.project_id,self.algorithm_id,self.get_locked(),self.live_mode
        self._config_bound()  # Native getters cannot silently rebase the scope.
        if (live is not False or type(project) is not int or project!=self._parent_identity[0]
                or locked is not True or type(job) is not str or re.fullmatch('[0-9a-f]{32}',job) is None
                or job==self._parent_identity[1]):raise ValueError('reader custody refused')
        if self._job is None:self._job=job;self._report['actual_child_job_id']=job
        elif self._job!=job:raise ValueError('reader job drift refused')
        return ('tpr-cmp28/result-reader/'+self._parent_identity[5]+'/'+self._config_sha256+'/'
            +str(project)+'/'+job+'/')

    def _effect(self,phase,call):
        self._phase=phase;self._bound()
        if phase=='parse':
            self._parse_calls+=1
            if self._parse_calls>300050:raise ValueError('reader parse budget refused')
        if phase=='hash':
            self._hash_calls+=1
            if self._hash_calls>10000:raise ValueError('reader hash budget refused')
        try:value=call()
        except BaseException as first:
            try:self._bound()
            except BaseException as second:
                if isinstance(second,KeyboardInterrupt):raise second
                if isinstance(first,KeyboardInterrupt) or not isinstance(first,Exception):raise first
                if not isinstance(second,Exception):raise second
            raise
        self._bound();return value

    def _claim(self,kind,descriptor):
        prefix=self._bound();token=(kind,descriptor['key'],descriptor['sha256'])
        if token in self._claim_spent or self._claims>=1026:raise ValueError('reader claim spent')
        self._claim_spent.add(token);ordinal=self._claims;self._claims+=1
        body={'schema':'tpr-cmp28-native-result-access-v1','operation_id':READER_CONFIG['operation_id'],
            'root_head':READER_CONFIG['git_head'],'reader_config_sha256':READER_CONFIG_SHA256,
            'project_id':self.project_id,'actual_child_job_id':self._job,'parent_job_id':READER_CONFIG['binding']['job_id'],
            'parent_config_sha256':READER_CONFIG['binding']['config_sha256'],
            'parent_index_sha256':READER_CONFIG['binding']['envelopes']['index']['sha256'],
            'kind':kind,'resource':descriptor,'spent_before_effect':True,'same_node_readback_only':True,
            'backend_durability_proven':False,'external_manifest_required':True,'outcome_permission_granted':False}
        raw=json.dumps(body,sort_keys=True,separators=(',',':'),allow_nan=False).encode('ascii')
        if not 0<len(raw)<=4096:raise ValueError('reader claim bound')
        key=prefix+f'access-{ordinal:04d}.json'
        exists=self._effect('claim_contains',lambda:self.object_store.contains_key(key))
        if type(exists) is not bool or exists:raise ValueError('reader claim exists or unknown')
        if self._effect('claim_save',lambda:self.object_store.save_bytes(key,raw)) is not True:
            raise ValueError('reader claim save unproved')
        observed=self._effect('claim_readback',lambda:self.object_store.read_bytes(key))
        observed=self._effect('byte_conversion',lambda:R_native_bytes(observed,len(raw)))
        if observed!=raw or self._effect('hash',lambda:hashlib.sha256(observed).hexdigest())!=hashlib.sha256(raw).hexdigest():
            raise ValueError('reader claim readback refused')
        self._report['claims_same_node_verified']+=1

    def _read(self,kind,descriptor,maximum):
        if (kind not in ('index','chunk') or type(descriptor) is not dict or set(descriptor)!={'key','bytes','sha256'}
                or type(descriptor['bytes']) is not int or not 0<descriptor['bytes']<=maximum
                or type(descriptor['key']) is not str or not descriptor['key'].startswith(READER_CONFIG['parent_prefix'])
                or re.fullmatch('[0-9a-f]{64}',descriptor['sha256']) is None):
            raise ValueError('reader artifact scope refused')
        self._claim(kind,descriptor)
        if self._reads>=1025:raise ValueError('reader read budget')
        self._reads+=1
        observed=self._effect('read_'+kind,lambda:self.object_store.read_bytes(descriptor['key']))
        raw=self._effect('byte_conversion',lambda:R_native_bytes(observed,descriptor['bytes']))
        if len(raw)!=descriptor['bytes'] or len(raw)>maximum or self._effect('hash',lambda:hashlib.sha256(raw).hexdigest())!=descriptor['sha256']:
            raise ValueError('reader artifact hash or length refused')
        self._private_bytes+=len(raw)
        if self._private_bytes>258*1024*1024:raise ValueError('reader cumulative byte budget')
        return raw

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
                'bytes':len(index),'journal_total_bytes':sum(map(len,chunks)),'maximum_records':300000,'maximum_chunks':1024,'maximum_parse_calls':300050}
            self._claim('replay',replay)
            report=self._effect('replay',lambda:C_replay_chunks(summary,index,config,calendar,original,binding=binding,chunks=chunks))
            self._report.update(status='completed_supplied_journal_replay',phase='complete',completed_read_replay=True,completion_report=report)
        except KeyboardInterrupt:raise KeyboardInterrupt('CMP28 reader cancelled') from None
        except Exception as error:
            kind=next((item.__name__ for item in (C_CompletionRefusal,E_EvidenceError,ValueError,TypeError,KeyError,AttributeError,OverflowError) if type(error) is item),'Exception')
            self._error('private_read_or_replay_refused',kind)
        except BaseException:raise ReaderStopped('CMP28 reader stopped') from None

    def on_data(self,data):
        if self._disabled:return
        self._clock_bars+=len(data.bars)
        if self._clock_bars>=1440:
            self._disabled=True;self._error('clock_bar_bound','Exception');self.quit('CMP28 reader clock stop')

    def on_end_of_algorithm(self):
        self._report.update(private_reads=self._reads,private_bytes=self._private_bytes,parse_calls=self._parse_calls,
            hash_calls=self._hash_calls,clock_bars=self._clock_bars)
        try:self._bound();self._report['end_runtime_custody']=True
        except KeyboardInterrupt:raise KeyboardInterrupt('CMP28 reader cancelled') from None
        except Exception:self._report['end_runtime_custody']=False
        except BaseException:raise ReaderStopped('CMP28 reader stopped') from None
        raw=json.dumps(self._report,sort_keys=True,separators=(',',':'),allow_nan=False)
        if len(raw.encode('ascii'))>32768:
            raw=json.dumps({'schema':'tpr-cmp28-native-private-result-reader-v1','status':'safe_report_bound_refused',
                'actual_child_job_id':self._job,'strategy_accepted':False,'canonical_admission':False})
        self.log('CMP28_PRIVATE_RESULT_READER_RESULT '+raw)
'''


def build_native_result_reader(*,public_sources,binding,summary_raw,config_raw,index_key,operation_id,git_head):
    """Return only main.py/report bytes. The caller owns all actual access."""
    if type(public_sources) is not dict or set(public_sources)!=set(PINS):_fail()
    for path,digest in PINS.items():
        raw=public_sources[path]
        if type(raw) is not bytes or not 0<len(raw)<=131072 or _sha(raw)!=digest:_fail()
    if (type(operation_id) is not str or re.fullmatch(r'TPR-CMP28-RESULT-READER-[A-Za-z0-9_.-]{1,100}',operation_id) is None
            or type(git_head) is not str or re.fullmatch('[0-9a-f]{40}',git_head) is None
            or type(binding) is not dict or type(summary_raw) is not bytes or not 0<len(summary_raw)<=512*1024
            or type(config_raw) is not bytes or not 0<len(config_raw)<=64*1024):_fail()
    try:
        e_nodes,e_names=_select(public_sources[PREFIX+'extended_evidence.py'],E_NAMES)
        m_nodes,m_names=_select(public_sources[PREFIX+'extended_metrics.py'],M_NAMES)
        c_nodes,c_names=_select(public_sources[PREFIX+'comparison_20261028_completion.py'])
        e={name:'E_'+name for name in e_names};m={name:'M_'+name for name in m_names};c={name:'C_'+name for name in c_names}
        aliases={'e':e,'evidence':e,'metrics':m}
        selected=(_render(e_nodes,e,{})+_render(m_nodes,m,aliases)+_render(c_nodes,c,aliases))
        # Guard all pure-consumer parse/hash invocations, preserving their exact
        # selected function bodies rather than inventing another JSON decoder.
        tree=ast.parse(selected)
        class Calls(ast.NodeTransformer):
            def visit_Call(self,node):
                node=self.generic_visit(node)
                if isinstance(node.func,ast.Name) and node.func.id in ('E_parse_json','C__sha'):
                    node.func.id={'E_parse_json':'_reader_parse','C__sha':'_reader_hash'}[node.func.id]
                return node
        tree=Calls().visit(tree);ast.fix_missing_locations(tree);selected=ast.unparse(tree)+'\n'
        native_nodes,_=_select(public_sources[PREFIX+'comparison_20261028_algorithm.py'],{'native_bytes','comparison_calendar'})
        selected+=_render(native_nodes,{'native_bytes':'R_native_bytes','comparison_calendar':'R_comparison_calendar','_fail':'C__fail'}, {})
        completion._closed(binding,completion.BINDING_KEYS)
        if (binding['schema']!='tpr-cmp28-completion-binding-v1' or binding['study_id']!=completion.STUDY
                or binding['arm'] not in completion.CANDIDATES or binding['candidate_id']!=completion.CANDIDATES[binding['arm']]
                or binding['terminal_status']!='Completed' or type(binding['project_id']) is not int
                or binding['project_id'] not in (37650980,37650453) or binding['arm']=='cap_off' and binding['project_id']!=37650980
                or type(binding['job_id']) is not str or re.fullmatch('[0-9a-f]{32}',binding['job_id']) is None
                or type(binding['attempt']) is not int or not 1<=binding['attempt']<=2**31-1
                or type(binding['operation_id']) is not str or re.fullmatch(r'TPR-CMP28-[A-Za-z0-9_.-]{1,150}',binding['operation_id']) is None):_fail()
        for name in ('terminal_evidence_sha256','config_sha256','policy_sha256','calendar_sha256',
                'source_template_closure_sha256','prior_attempts_looks_sha256','rendered_source_closure_sha256'):
            completion._hash(binding[name])
        templates=completion._sources(binding['template_source_hashes'],template=True)
        rendered=completion._sources(binding['rendered_source_hashes'],template=False)
        if (binding['source_template_closure_sha256']!=_sha(_wire({'schema':'tpr-cmp28-public-template-closure-v1','source_hashes':templates}))
                or binding['rendered_source_closure_sha256']!=_sha(_wire(rendered))):_fail()
        completion._closed(binding['envelopes'],completion.ENVELOPES)
        for name,maximum in completion.ENVELOPES.items():
            descriptor=binding['envelopes'][name];completion._closed(descriptor,('sha256','bytes'));completion._hash(descriptor['sha256'])
            if type(descriptor['bytes']) is not int or not 0<descriptor['bytes']<=maximum:_fail()
        prefix=('tpr-cmp28/evidence/'+binding['study_id']+'/'+binding['operation_id']+'/'+binding['config_sha256']
            +'/attempt-'+str(binding['attempt'])+'/'+str(binding['project_id'])+'/'+binding['job_id']+'/')
        if index_key!=prefix+'index.json':_fail()
        for name,raw in (('summary',summary_raw),('config',config_raw)):
            descriptor=binding['envelopes'][name]
            if descriptor['sha256']!=_sha(raw) or descriptor['bytes']!=len(raw):_fail()
        if _sha(config_raw)!=binding['config_sha256']:_fail()
        summary=completion.evidence.parse_json(summary_raw);parent_config=completion.evidence.parse_json(config_raw)
        multi=binding['arm']!='cap_off'
        completion._closed(summary,completion.SUMMARY_KEYS|({'signal_runtime_access'} if multi else set()))
        if any(summary[name] is not False for name in completion._FALSE_FIELDS) or summary['accepted_performance'] is not None:_fail()
        completion._closed(parent_config,completion.CONFIG_KEYS|({'signal_packet'} if multi else set()))
        for body in (summary,parent_config):
            if any(body[name] is not False for name in ('source_inputs_admitted','canonical_admission')):_fail()
            for name in ('study_id','candidate_id','arm','operation_id','attempt','project_id','policy_sha256','calendar_sha256','source_template_closure_sha256'):
                if not completion._same(body[name],binding[name]):_fail()
        config={'schema':'tpr-cmp28-native-result-reader-config-v1','operation_id':operation_id,'git_head':git_head,
            'public_source_hashes':dict(PINS),'binding':binding,'index_key':index_key,'parent_prefix':prefix,
            'summary_json':summary_raw.decode('ascii'),'parent_config_json':config_raw.decode('ascii'),
            'diagnostic_session':'2021-01-04','initialize_private_effects':False,'external_manifest_required':True}
        cfg=_wire(config);cfg_hash=_sha(cfg)
        source=(HEADER+selected+'READER_CONFIG_JSON = '+repr(cfg.decode('ascii'))+'\nREADER_CONFIG_SHA256 = '+repr(cfg_hash)
            +'\nREADER_CONFIG = json.loads(READER_CONFIG_JSON)\n'+NATIVE).encode('utf-8')
        if not 0<len(source)<=60000:_fail()
        compile(ast.parse(source),'main.py','exec')
        report={'schema':'tpr-cmp28-native-result-reader-build-v1','main_bytes':len(source),'main_sha256':_sha(source),
            'config_sha256':cfg_hash,'public_source_hashes':dict(PINS),'main_only_cloud_edit':True,'preserve_other_cloud_files':23,
            'diagnostic_session':'2021-01-04','max_private_index_reads':1,'max_index_bytes':2*1024*1024,
            'max_chunk_reads':1024,'max_chunk_bytes':512*1024,'max_journal_bytes':256*1024*1024,'max_records':300000,
            'max_claims':1026,'max_claim_bytes':4096,'max_parse_calls':300050,'max_hash_calls':10000,
            'max_clock_bars':1440,'retains_all_supplied_chunks_in_native_memory':True,'initialize_private_effects':False,
            'native_origin_authenticated':False,'backend_durability_proven':False,'independent_reconciliation_proven':False,
            'source_inputs_admitted':False,'data_rights_authenticated':False,'historical_pit_authenticated':False,
            'native_permission':False,'strategy_accepted':False,'canonical_admission':False,'accepted_performance':None,
            'external_manifest_required':True,'new_jobs':0,'new_economic_looks':0}
    except (ValueError,TypeError,KeyError,UnicodeError,SyntaxError,OverflowError,StopIteration):_fail()
    return source,_wire(report)+b'\n'
