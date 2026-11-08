"""Pure public-source W5 projection and six-cell local specification.

The original quote-aware cloud base remains immutable provenance. A separately
named W5 base has declared period/capital-epoch/result changes and the
owner-directed buy cash bound. All source bytes are supplied; this module
cannot read data, contact QC or grant a run.
"""
import ast
import copy
import dataclasses
import hashlib
import json
import re

from scripts import arv2_r298_common_price_batch as previous
from scripts import arv2_r327_available_history_period as period
from research.analyst_revisions_v2_qc import newrule_available_history_comparison_runtime as base
from research.analyst_revisions_v2_qc import newrule_available_history_common_price_runtime as runtime

common,quote,plain=previous.common,previous.common.frozen,previous.plain
native,vendor=previous.native,previous.vendor
SCHEMA='arv2-r327-available-history-public-batch-v1'
CELL_SCHEMA='arv2-r327-available-history-public-projection-v2'
PATCHER_NAME='arv2_r327_available_history_projection.py'
BASE_NAME='newrule_available_history_comparison_runtime.py'
DRIVER_NAME='newrule_available_history_common_price_runtime.py'
AVAILABLE_NAMES=(BASE_NAME,DRIVER_NAME)
ENGINE_START_SESSION='2021-09-01'
AVAILABLE_SOURCE_PINS={BASE_NAME:'7b32ec439553089fbd9b3ffd5fabb708bc823fffca479c8f941dbfe185b33150',
 DRIVER_NAME:'1478c1a5008409f44d52622002d6e4ea0999222a65580ad8bc9e5a7fa805fb3e'}
PERIOD_SOURCE_PIN='722cffeae9fbebcd9bca656c8994273d2b1fb36f6d3e269a018c8fb18e5b7b18'
CELL_ORDER=previous.CELL_ORDER
MAX_SOURCE_BYTES,MAX_TOTAL_BYTES,MAX_RECORD_BYTES=64000,2*1024*1024,131072
FALSE_FLAGS={**previous.FALSE_FLAGS,'QC_or_Safari_access':False,'runtime_project_currently_verified':False,
 'input_DATA_reauthenticated':False,'native_book_point_coverage_proven':False,'source_assignments_changed':False,
 'old_full_period_candidate_admitted':False,'prior_results_relabelled':False}
FINITE=frozenset(('source_inventory','source_pin','source_bound','period','base_delta','quote','base_semantics',
 'main_anchor','main_semantics','profile','context','project','cell','batch','projection','geometry','unknown'))
BASE_CHANGES=(
 ('SCHEMA = "arv2-accepted-risk-newrule-comparison-profile-v1"','SCHEMA = "arv2-r327-available-history-comparison-profile-v1"',1),
 ('START_SESSION = "2021-01-04"','START_SESSION = "2021-11-01"\nFIRST_REFERENCE_CLOSE = "2021-10-29"\nRESEARCH_EPOCH_ID = "R327-20261027-available-history-v1"\nFULL_AXIS_COUNT = 3466\nFULL_AXIS_SHA256 = "4ac84a2d01e18691a152812851857195ef56dac16b82ceb72bcf7dd068f86585"',1),
 ('META_STATISTIC = "ARV2_NEWRULE_META"','META_STATISTIC = "ARV2_AVAILABLE_HISTORY_META"',1),
 ('MONTHLY_STATISTIC = "ARV2_NEWRULE_MONTHLY"','MONTHLY_STATISTIC = "ARV2_AVAILABLE_HISTORY_MONTHLY"',1),
 ('    targets.cohort(universe_count)\n','    require(type(axis) is tuple and len(axis) == FULL_AXIS_COUNT\n            and all(type(value) is str and len(value) == 10 for value in axis)\n            and targets.digest(axis) == FULL_AXIS_SHA256, "available_history_full_axis")\n    require(START_SESSION in axis and axis.index(START_SESSION) > 0\n            and axis[axis.index(START_SESSION) - 1] == FIRST_REFERENCE_CLOSE, "available_history_prior_close")\n    targets.cohort(universe_count)\n',1),
 ('f"arv2-newrule-{universe_count}-ar{ar_percent}-2026-v1"','f"arv2-r327-{universe_count}-ar{ar_percent}-2021Nov01-2026Oct13-v1"',1),
 ('    seed = {"schema": SCHEMA,\n','    seed = {"schema": SCHEMA, "research_epoch_id": RESEARCH_EPOCH_ID,\n        "first_reference_close": FIRST_REFERENCE_CLOSE,\n        "initial_state": "new_epoch_empty_positions_and_orders_USD1000000",\n',1),
 ('first_2021Jan04_STARTING_CASH','first_2021Nov01_new_epoch_STARTING_CASH',1),
 ('"arv2-newrule-comparison-result-v1"','"arv2-r327-available-history-comparison-result-v1"',2),
 ('"arv2-newrule-monthly-return-v1"','"arv2-r327-available-history-monthly-return-v1"',2),
 ('        require(not self._current_holding_census(), "initial_holdings")\n','        require(not self._current_holding_census(), "initial_holdings")\n        require(not tuple(self._algorithm.transactions.get_open_orders()), "initial_open_orders")\n',1))
_OLD_CONSTANTS=('SCHEMA','START_SESSION','META_STATISTIC','MONTHLY_STATISTIC')
_NEW_CONSTANTS=('FIRST_REFERENCE_CLOSE','RESEARCH_EPOCH_ID','FULL_AXIS_COUNT','FULL_AXIS_SHA256')
_PERIOD_METHODS=('initialize','on_end_of_algorithm')
_QUOTE_METHODS=('__init__','_quote_snapshot','fee_basis','_current_execution_price','_submit_market','on_after_open','on_order_event')
# Owner-directed W5 cash bound (section 330, ARV2R328-004). LEAN's pre-trade
# buying-power check values a market buy at security.Price, which can be a stale
# trade above the authenticated ask, so a cash-limited buy is sized on the larger
# of the two. Ask fill price, fee basis and prior-close targets are unchanged.
CASH_BOUND_METHOD='on_after_open'
CASH_BOUND_CHANGE=('price = self._current_execution_price(security, 1)',
 'try:\n    price = max(self._current_execution_price(security, 1), number(security.price, positive=True))\n'
 'except targets.NewruleError:\n    raise\n'
 'except Exception:\n    raise targets.NewruleError("quote_execution_engine_price") from None')
CASH_BOUND_FIELD=('buy_cash_bound','floor_current_cash_divided_by_max_of_ask_and_engine_security_price_times_1point001;prior_RAW_close_target_quantities_unchanged')


class Refused(ValueError):pass


def require(value,code):
    if not value:raise Refused(code)


def finite(error):
    args=BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args)==1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')
def sha(raw):return hashlib.sha256(raw).hexdigest()
def digest(value):return sha(canonical(value))
def pin(raw):return {'byte_count':len(raw),'sha256':sha(raw)}
def _dump(value):return ast.dump(value,include_attributes=False)
def _hash(value):return type(value) is str and re.fullmatch('[0-9a-f]{64}',value) is not None


def _node(owner,name,kind=ast.FunctionDef):
    values=[node for node in owner.body if isinstance(node,kind) and node.name==name]
    require(len(values)==1,'base_semantics');return values[0]


def _assignment(tree,name):
    values=[node for node in tree.body if isinstance(node,ast.Assign) and len(node.targets)==1
        and isinstance(node.targets[0],ast.Name) and node.targets[0].id==name]
    require(len(values)==1,'base_semantics');return values[0]


def _replace_node(owner,old,new):owner.body[owner.body.index(old)]=copy.deepcopy(new)


def policy_profile_fields():
    fields=quote.policy_profile_fields();require(CASH_BOUND_FIELD[0] in fields,'quote')
    return {**fields,CASH_BOUND_FIELD[0]:CASH_BOUND_FIELD[1]}


def _quoted_profile(node,fields):
    result=copy.deepcopy(node);require(isinstance(result.body[-1],ast.Return),'base_semantics')
    result.body[-1:-1]=ast.parse('seed["candidate_id"] += "-quote-aware-v1"\nseed.update('+repr(fields)+')').body
    return result


def _cash_bound(method,old,new):
    """Replace the single exact cash-bound statement anywhere in one method."""
    result=copy.deepcopy(method);before,after=ast.parse(old).body[0],ast.parse(new).body[0]
    sites=[(block,index) for node in ast.walk(result) for name in ('body','orelse')
        for block in (getattr(node,name,None),) if type(block) is list
        for index,item in enumerate(block) if _dump(item)==_dump(before)]
    require(len(sites)==1,'base_semantics');block,index=sites[0];block[index]=after;return result


def _period_base(old_host_raw,available_raw,quoted_raw):
    require(sha(old_host_raw)==previous.PUBLIC_SOURCE_PINS[common.BASE_NAME]
        and sha(quoted_raw)==common.runtime.FROZEN_BASE_SHA256,'quote')
    expected=old_host_raw.decode('ascii')
    for old,new,count in BASE_CHANGES:
        require(expected.count(old)==count,'base_delta');expected=expected.replace(old,new)
    require(expected.encode('ascii')==available_raw,'base_delta')
    old_host,new_host,original=ast.parse(old_host_raw),ast.parse(available_raw),ast.parse(quoted_raw)
    tree=copy.deepcopy(original)
    require(_dump(_node(original,'make_profile'))==_dump(_quoted_profile(_node(old_host,'make_profile'),quote.policy_profile_fields())),'quote')
    for name in _OLD_CONSTANTS:_replace_node(tree,_assignment(tree,name),_assignment(new_host,name))
    insertion=tree.body.index(_assignment(tree,'START_SESSION'))+1
    tree.body[insertion:insertion]=[copy.deepcopy(_assignment(new_host,name)) for name in _NEW_CONSTANTS]
    _replace_node(tree,_node(tree,'make_profile'),_quoted_profile(_node(new_host,'make_profile'),policy_profile_fields()))
    _replace_node(tree,_node(tree,'validate_result_statistics'),_node(new_host,'validate_result_statistics'))
    owner=_node(tree,'NewruleComparisonDriver',ast.ClassDef)
    original_owner=_node(original,'NewruleComparisonDriver',ast.ClassDef)
    new_owner=_node(new_host,'NewruleComparisonDriver',ast.ClassDef)
    old_owner=_node(old_host,'NewruleComparisonDriver',ast.ClassDef)
    for name in _PERIOD_METHODS:
        require(_dump(_node(original_owner,name))==_dump(_node(old_owner,name)),'quote')
        _replace_node(owner,_node(owner,name),_node(new_owner,name))
    for name in _QUOTE_METHODS:require(_dump(_node(owner,name))==_dump(_node(original_owner,name)),'base_semantics')
    bounded=_cash_bound(_node(owner,CASH_BOUND_METHOD),*CASH_BOUND_CHANGE)
    require(_dump(_cash_bound(bounded,*reversed(CASH_BOUND_CHANGE)))==_dump(_node(original_owner,CASH_BOUND_METHOD)),'base_semantics')
    _replace_node(owner,_node(owner,CASH_BOUND_METHOD),bounded)
    restored=copy.deepcopy(tree)
    restored.body=[node for node in restored.body if not (isinstance(node,ast.Assign) and len(node.targets)==1
        and isinstance(node.targets[0],ast.Name) and node.targets[0].id in _NEW_CONSTANTS)]
    for name in _OLD_CONSTANTS:_replace_node(restored,_assignment(restored,name),_assignment(original,name))
    for name in ('make_profile','validate_result_statistics'):_replace_node(restored,_node(restored,name),_node(original,name))
    restored_owner=_node(restored,'NewruleComparisonDriver',ast.ClassDef)
    for name in (*_PERIOD_METHODS,CASH_BOUND_METHOD):_replace_node(restored_owner,_node(restored_owner,name),_node(original_owner,name))
    require(_dump(restored)==_dump(original),'base_semantics')
    ast.fix_missing_locations(tree);raw=(ast.unparse(tree)+'\n').encode('ascii')
    require(0<len(raw)<=MAX_SOURCE_BYTES,'source_bound');compile(b'from AlgorithmImports import *\n'+raw,BASE_NAME,'exec')
    return raw


def _main(raw,strategy,profile,native_context,vendor_context):
    original_raw=common._main(raw,strategy,profile,native_context,vendor_context)
    original=ast.parse(original_raw);tree=copy.deepcopy(original)
    imports=[node for node in tree.body if isinstance(node,ast.ImportFrom) and node.module==common.DRIVER_NAME[:-3]]
    require(len(imports)==1,'main_anchor');imports[0].module=DRIVER_NAME[:-3]
    calls=[node for node in ast.walk(tree) if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute)
        and node.func.attr=='set_start_date']
    require(len(calls)==1 and not calls[0].keywords and [ast.literal_eval(node) for node in calls[0].args]==[2020,11,1],'main_anchor')
    calls[0].args=[ast.Constant(2021),ast.Constant(9),ast.Constant(1)]
    restored=copy.deepcopy(tree)
    next(node for node in restored.body if isinstance(node,ast.ImportFrom) and node.module==DRIVER_NAME[:-3]).module=common.DRIVER_NAME[:-3]
    start=next(node for node in ast.walk(restored) if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute)
        and node.func.attr=='set_start_date');start.args=[ast.Constant(2020),ast.Constant(11),ast.Constant(1)]
    require(_dump(restored)==_dump(original),'main_semantics')
    ast.fix_missing_locations(tree);projected=(ast.unparse(tree)+'\n').encode('ascii')
    compile(projected,'main.py','exec');return projected


def _profile(axis,size,arm,pins):
    value=base.make_profile(axis,package_sha256=plain.PLAIN_PACKAGE_SHA256,lineage_sha256=plain.bridge.parent.LINEAGE,
        universe_count=size,ar_percent=arm,source_pins=pins)
    seed={key:item for key,item in value.items() if key!='profile_sha256'}
    seed['candidate_id']+='-quote-aware-v1';seed.update(policy_profile_fields())
    return {**seed,'profile_sha256':digest(seed)}


def _sources(public_sources,addons,quote_raw,common_raw,available_pairs,period_raw,patcher_raw,patcher_pin):
    try:previous._sources(public_sources,addons,quote_raw,common_raw)
    except previous.Refused as error:raise Refused(previous.finite(error)) from None
    require(type(available_pairs) is tuple and len(available_pairs)==2
        and all(type(item) is tuple and len(item)==2 and type(item[0]) is str for item in available_pairs)
        and tuple(name for name,_ in available_pairs)==AVAILABLE_NAMES,'source_inventory')
    for name,raw in available_pairs:
        require(type(raw) is bytes and raw.isascii() and 0<len(raw)<=MAX_SOURCE_BYTES,'source_bound')
        require(sha(raw)==AVAILABLE_SOURCE_PINS[name],'source_pin')
    require(type(period_raw) is bytes and 0<len(period_raw)<=MAX_SOURCE_BYTES and sha(period_raw)==PERIOD_SOURCE_PIN
        and period_raw.isascii(),'source_pin')
    require(type(patcher_raw) is bytes and patcher_raw.isascii() and 0<len(patcher_raw)<=MAX_SOURCE_BYTES
        and _hash(patcher_pin) and sha(patcher_raw)==patcher_pin,'source_pin')


def _profile_main_join(source_pairs,profile):
    tree=ast.parse(dict(source_pairs)['main.py']);constants={}
    for node in tree.body:
        if (isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name)
            and node.targets[0].id in ('COMMON_PRICE_PROFILE','NATIVE_SOURCE_CONTEXT','VENDOR_SOURCE_CONTEXT')):
            constants[node.targets[0].id]=ast.literal_eval(node.value)
    require(set(constants)=={'COMMON_PRICE_PROFILE','NATIVE_SOURCE_CONTEXT','VENDOR_SOURCE_CONTEXT'}
        and constants['COMMON_PRICE_PROFILE']==profile
        and digest(constants['NATIVE_SOURCE_CONTEXT'])==profile['native_source_context_sha256']
        and digest(constants['VENDOR_SOURCE_CONTEXT'])==profile['vendor_source_context_sha256'],'projection')
    starts=[node for node in ast.walk(tree) if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute)
        and node.func.attr=='set_start_date']
    require(len(starts)==1 and [ast.literal_eval(node) for node in starts[0].args]==[2021,9,1],'projection')


@dataclasses.dataclass(frozen=True,slots=True)
class Projection:
    projection_sha256:str
    record_bytes:bytes=dataclasses.field(repr=False)
    profile_bytes:bytes=dataclasses.field(repr=False)
    source_pairs:tuple=dataclasses.field(repr=False)

    def to_record(self):
        require(type(self.record_bytes) is bytes and len(self.record_bytes)<=MAX_RECORD_BYTES
            and sha(self.record_bytes)==self.projection_sha256 and type(self.profile_bytes) is bytes
            and type(self.source_pairs) is tuple,'projection')
        record=json.loads(self.record_bytes);profile=runtime.validate_profile(json.loads(self.profile_bytes))
        require(canonical(record)==self.record_bytes and canonical(profile)==self.profile_bytes
            and set(record)=={'schema','profile_sha256','strategy_profile_sha256','runtime_project_id','universe_count','ar_percent',
                'native_source_context_sha256','vendor_source_context_sha256','frozen_quote_projection_sha256',
                'frozen_quote_profile_sha256','frozen_quote_base_sha256','available_history_quote_base_pin',
                'original_available_source_pins','period_source_pin','period_sha256','research_epoch_id','patcher_sha256','source_files',
                'engine_start_session','evaluation_start_session',
                'all_old_quote_files_unchanged_except_Main','period_base_inverse_AST_equals_frozen_quote_base',
                'quote_methods_AST_unchanged_except_declared_cash_bound','input_package_and_source_assignments_unchanged',*FALSE_FLAGS}
            and record['schema']==CELL_SCHEMA and record['profile_sha256']==profile['profile_sha256']
            and record['strategy_profile_sha256']==profile['strategy_profile_sha256']
            and record['source_files']==[{'project_path':name,'byte_count':len(raw),'content_sha256':sha(raw)} for name,raw in self.source_pairs]
            and tuple(name for name,_ in self.source_pairs)==quote.comparison.bridge.parent.FILE_NAMES+common.ADDON_NAMES[:-1]+AVAILABLE_NAMES
            and all(record[key] is False for key in FALSE_FLAGS),'projection')
        require(record['frozen_quote_projection_sha256']==common.BASE_PROJECTION and record['frozen_quote_profile_sha256']==common.BASE_PROFILE
            and record['research_epoch_id']==base.RESEARCH_EPOCH_ID and _hash(record['patcher_sha256'])
            and record['engine_start_session']==ENGINE_START_SESSION and record['evaluation_start_session']==base.START_SESSION
            and all(record[key] is True for key in ('all_old_quote_files_unchanged_except_Main',
                'period_base_inverse_AST_equals_frozen_quote_base','quote_methods_AST_unchanged_except_declared_cash_bound',
                'input_package_and_source_assignments_unchanged')),'projection')
        require(record['frozen_quote_base_sha256']==common.runtime.FROZEN_BASE_SHA256
            and record['available_history_quote_base_pin']==pin(dict(self.source_pairs)[BASE_NAME])
            and record['original_available_source_pins']==AVAILABLE_SOURCE_PINS
            and record['period_source_pin']==PERIOD_SOURCE_PIN and record['period_sha256']==period.make_period(plain.bridge.frozen.october._sessions())['period_sha256'],
            'projection')
        require(profile['source_pins']=={**{name:sha(raw) for name,raw in self.source_pairs if name!='main.py'},
            PATCHER_NAME:record['patcher_sha256']}
            and profile['strategy_profile']['source_pins']==profile['source_pins']
            and sha(dict(self.source_pairs)[common.BASE_NAME])==common.runtime.FROZEN_BASE_SHA256,'projection')
        for key in ('universe_count','ar_percent','runtime_project_id','native_source_context_sha256','vendor_source_context_sha256'):
            require(type(record[key]) is type(profile[key]) and record[key]==profile[key],'projection')
        _profile_main_join(self.source_pairs,profile)
        return record


def _cell(pairs,cloud_addons,axis,view,size,arm,project,native_context,vendor_context,patcher_pin):
    pins={name:sha(raw) for name,raw in (*pairs,*cloud_addons) if name!='main.py'};pins[PATCHER_NAME]=patcher_pin
    strategy=_profile(axis,size,arm,pins)
    require(strategy['evaluation_sessions']==view['evaluation_sessions'] and strategy['decision_sessions']==view['decision_sessions']
        and strategy['research_epoch_id']==view['research_epoch_id'],'period')
    profile=runtime.make_profile(strategy,runtime_project_id=project,native_source_context_sha256=digest(native_context),
        vendor_source_context_sha256=digest(vendor_context),source_pins=pins)
    main=_main(dict(pairs)['main.py'],strategy,profile,native_context,vendor_context)
    output=tuple((name,main if name=='main.py' else raw) for name,raw in pairs)+cloud_addons
    require(len(output)==19 and len({name for name,_ in output})==19 and all(type(raw) is bytes and 0<len(raw)<=MAX_SOURCE_BYTES for _,raw in output)
        and sum(len(raw) for _,raw in output)<=MAX_TOTAL_BYTES,'source_bound')
    record={'schema':CELL_SCHEMA,'profile_sha256':profile['profile_sha256'],'strategy_profile_sha256':strategy['profile_sha256'],
        'runtime_project_id':project,'universe_count':size,'ar_percent':arm,'native_source_context_sha256':digest(native_context),
        'vendor_source_context_sha256':digest(vendor_context),'frozen_quote_projection_sha256':common.BASE_PROJECTION,
        'frozen_quote_profile_sha256':common.BASE_PROFILE,'frozen_quote_base_sha256':common.runtime.FROZEN_BASE_SHA256,
        'available_history_quote_base_pin':pin(dict(cloud_addons)[BASE_NAME]),'original_available_source_pins':dict(AVAILABLE_SOURCE_PINS),
        'period_source_pin':PERIOD_SOURCE_PIN,'period_sha256':view['period_sha256'],'research_epoch_id':view['research_epoch_id'],
        'engine_start_session':ENGINE_START_SESSION,'evaluation_start_session':base.START_SESSION,
        'patcher_sha256':patcher_pin,'source_files':[{'project_path':name,'byte_count':len(raw),'content_sha256':sha(raw)} for name,raw in output],
        'all_old_quote_files_unchanged_except_Main':True,'period_base_inverse_AST_equals_frozen_quote_base':True,
        'quote_methods_AST_unchanged_except_declared_cash_bound':True,'input_package_and_source_assignments_unchanged':True,**FALSE_FLAGS}
    raw=canonical(record);value=Projection(sha(raw),raw,canonical(profile),output);value.to_record();return value


def _metadata(specs):
    require(type(specs) is tuple and len(specs)==6 and all(type(spec) is Projection for spec in specs),'batch')
    cells=[];shared=None;baseline=None;period_sha=None;project=None
    for (size,arm),spec in zip(CELL_ORDER,specs,strict=True):
        record=spec.to_record();profile=runtime.validate_profile(json.loads(spec.profile_bytes))
        require((record['universe_count'],record['ar_percent'])==(size,arm),'geometry')
        non_main=tuple((name,raw) for name,raw in spec.source_pairs if name!='main.py')
        common_seed={key:value for key,value in profile.items() if key not in ('candidate_id','profile_sha256','strategy_profile','strategy_profile_sha256','universe_count','ar_percent')}
        strategy_seed={key:value for key,value in profile['strategy_profile'].items() if key not in ('candidate_id','profile_sha256','universe_count','ar_percent')}
        if shared is None:shared=non_main;baseline=(common_seed,strategy_seed);period_sha=record['period_sha256'];project=profile['runtime_project_id']
        require(non_main==shared and (common_seed,strategy_seed)==baseline and record['period_sha256']==period_sha
            and profile['runtime_project_id']==project,'geometry')
        manifest={'schema':SCHEMA+'-source-manifest','runtime_project_id':project,'profile_sha256':profile['profile_sha256'],'source_files':record['source_files']}
        cells.append({'universe_count':size,'ar_percent':arm,'candidate_id':profile['candidate_id'],
            'common_profile_sha256':profile['profile_sha256'],'strategy_profile_sha256':profile['strategy_profile_sha256'],
            'profile_pin':pin(spec.profile_bytes),'projection_pin':pin(spec.record_bytes),'projection_sha256':spec.projection_sha256,
            'source_manifest_pin':pin(canonical(manifest)),'main_pin':pin(dict(spec.source_pairs)['main.py']),
            'source_file_count':len(spec.source_pairs),'source_files':record['source_files']})
    require(all(len({row[key] if key.endswith('sha256') else row[key]['sha256'] for row in cells})==6
        for key in ('common_profile_sha256','strategy_profile_sha256','projection_sha256','main_pin')),'geometry')
    return {'schema':SCHEMA,'runtime_project_id':project,'period_sha256':period_sha,'research_epoch_id':base.RESEARCH_EPOCH_ID,
        'engine_start_session':ENGINE_START_SESSION,
        'evaluation_first':base.START_SESSION,'evaluation_last':base.END_SESSION,'first_reference_close':base.FIRST_REFERENCE_CLOSE,
        'starting_cash':'1000000','initial_state':'new_epoch_empty_positions_and_orders_USD1000000',
        'cell_count':6,'cell_order':[list(value) for value in CELL_ORDER],'cells':cells,
        'shared_non_main_source_files':[{'project_path':name,**pin(raw)} for name,raw in shared],
        'all19_sources_equal_except_Main':True,'same_source_policy_all_six_cells':True,
        'frozen_quote_base_sha256':common.runtime.FROZEN_BASE_SHA256,
        'available_history_quote_base_pin':pin(dict(shared)[BASE_NAME]),'period_source_pin':PERIOD_SOURCE_PIN,
        'original_public_source_pins':dict(previous.PUBLIC_SOURCE_PINS),'original_addon_source_pins':dict(previous.ADDON_SOURCE_PINS),
        'original_available_source_pins':dict(AVAILABLE_SOURCE_PINS),'AR_manifest_pin':dict(previous.AR_MANIFEST_PIN),
        'AR_catalog_pin':dict(previous.AR_CATALOG_PIN),'native_source_context_sha256':native.SOURCE_CONTEXT_SHA256,
        'vendor_source_context_sha256':baseline[0]['vendor_source_context_sha256'],
        'QC_hold':'local_preparation_only_no_current_project_source_rights_capacity_compile_or_run_verification',**FALSE_FLAGS}


def validate_batch_record(value):
    """Validate pinned public metadata only; actual source bytes stay external."""
    keys={'schema','runtime_project_id','period_sha256','research_epoch_id','engine_start_session','evaluation_first','evaluation_last','first_reference_close',
        'starting_cash','initial_state','cell_count','cell_order','cells','shared_non_main_source_files','all19_sources_equal_except_Main',
        'same_source_policy_all_six_cells','frozen_quote_base_sha256','available_history_quote_base_pin','period_source_pin',
        'original_public_source_pins','original_addon_source_pins','original_available_source_pins','AR_manifest_pin','AR_catalog_pin',
        'native_source_context_sha256','vendor_source_context_sha256','QC_hold',*FALSE_FLAGS}
    require(type(value) is dict and set(value)==keys and value['schema']==SCHEMA
        and type(value['runtime_project_id']) is int and 0<value['runtime_project_id']<=2147483647
        and value['research_epoch_id']==base.RESEARCH_EPOCH_ID and value['evaluation_first']==base.START_SESSION
        and value['engine_start_session']==ENGINE_START_SESSION
        and value['evaluation_last']==base.END_SESSION and value['first_reference_close']==base.FIRST_REFERENCE_CLOSE
        and value['starting_cash']=='1000000' and value['initial_state']=='new_epoch_empty_positions_and_orders_USD1000000'
        and type(value['cell_count']) is int and value['cell_count']==6 and value['cell_order']==[list(row) for row in CELL_ORDER]
        and value['all19_sources_equal_except_Main'] is value['same_source_policy_all_six_cells'] is True
        and value['frozen_quote_base_sha256']==common.runtime.FROZEN_BASE_SHA256
        and value['period_source_pin']==PERIOD_SOURCE_PIN
        and value['original_public_source_pins']==previous.PUBLIC_SOURCE_PINS
        and value['original_addon_source_pins']==previous.ADDON_SOURCE_PINS
        and value['original_available_source_pins']==AVAILABLE_SOURCE_PINS
        and value['AR_manifest_pin']==previous.AR_MANIFEST_PIN and value['AR_catalog_pin']==previous.AR_CATALOG_PIN
        and value['native_source_context_sha256']==native.SOURCE_CONTEXT_SHA256
        and value['QC_hold']=='local_preparation_only_no_current_project_source_rights_capacity_compile_or_run_verification'
        and all(value[key] is False for key in FALSE_FLAGS),'batch')
    view=period.make_period(plain.bridge.frozen.october._sessions());require(value['period_sha256']==view['period_sha256'],'period')
    expected_vendor={'schema':vendor.fmt.SCHEMA+'-QC-context','runtime_project_id':value['runtime_project_id'],
        'manifest_pin':dict(previous.AR_MANIFEST_PIN),'catalog_pin':dict(previous.AR_CATALOG_PIN),
        'object_key_prefix':str(value['runtime_project_id'])+'/arv2/r326-common/'+previous.AR_MANIFEST_PIN['sha256']+'/',
        'AP_fact_sha256':vendor.fmt.AP_FACT_SHA256,'AP_authentication_sha256':vendor.fmt.AP_AUTH_SHA256}
    require(value['vendor_source_context_sha256']==digest(expected_vendor),'context')
    expected_names=quote.comparison.bridge.parent.FILE_NAMES+common.ADDON_NAMES[:-1]+AVAILABLE_NAMES
    shared=value['shared_non_main_source_files'];require(type(shared) is list and len(shared)==18,'batch')
    expected_shared=tuple(name for name in expected_names if name!='main.py')
    for row in shared:
        require(type(row) is dict and set(row)=={'project_path','byte_count','sha256'} and type(row['byte_count']) is int
            and 0<row['byte_count']<=MAX_SOURCE_BYTES and _hash(row['sha256']),'batch')
    require(tuple(row['project_path'] for row in shared)==expected_shared,'batch')
    require(value['available_history_quote_base_pin']=={key:next(row for row in shared if row['project_path']==BASE_NAME)[key]
        for key in ('byte_count','sha256')},'batch')
    require(type(value['cells']) is list and len(value['cells'])==6,'batch')
    for (size,arm),row in zip(CELL_ORDER,value['cells'],strict=True):
        require(type(row) is dict and set(row)=={'universe_count','ar_percent','candidate_id','common_profile_sha256',
            'strategy_profile_sha256','profile_pin','projection_pin','projection_sha256','source_manifest_pin','main_pin',
            'source_file_count','source_files'} and type(row['universe_count']) is type(row['ar_percent']) is int
            and (row['universe_count'],row['ar_percent'])==(size,arm)
            and row['candidate_id']==f'arv2-r327-{size}-ar{arm}-2021Nov01-2026Oct13-v1-quote-aware-v1-common-RAW-W5-v1'
            and type(row['source_file_count']) is int and row['source_file_count']==19,'batch')
        for key in ('common_profile_sha256','strategy_profile_sha256','projection_sha256'):require(_hash(row[key]),'batch')
        for key in ('profile_pin','projection_pin','source_manifest_pin','main_pin'):
            item=row[key];require(type(item) is dict and set(item)=={'byte_count','sha256'} and type(item['byte_count']) is int
                and 0<item['byte_count']<=MAX_RECORD_BYTES and _hash(item['sha256']),'batch')
        require(row['projection_pin']['sha256']==row['projection_sha256'] and type(row['source_files']) is list
            and len(row['source_files'])==19,'batch')
        for item in row['source_files']:
            require(type(item) is dict and set(item)=={'project_path','byte_count','content_sha256'} and type(item['byte_count']) is int
                and 0<item['byte_count']<=MAX_SOURCE_BYTES and _hash(item['content_sha256']),'batch')
        require(tuple(item['project_path'] for item in row['source_files'])==expected_names,'batch')
        non_main=[{'project_path':item['project_path'],'byte_count':item['byte_count'],'sha256':item['content_sha256']}
            for item in row['source_files'] if item['project_path']!='main.py']
        main=next(item for item in row['source_files'] if item['project_path']=='main.py')
        manifest={'schema':SCHEMA+'-source-manifest','runtime_project_id':value['runtime_project_id'],
            'profile_sha256':row['common_profile_sha256'],'source_files':row['source_files']}
        require(non_main==shared and row['source_manifest_pin']==pin(canonical(manifest))
            and row['main_pin']=={'byte_count':main['byte_count'],'sha256':main['content_sha256']},'batch')
    require(all(len({row[key] if key.endswith('sha256') else row[key]['sha256'] for row in value['cells']})==6
        for key in ('common_profile_sha256','strategy_profile_sha256','projection_sha256','main_pin')),'geometry')
    require(len(canonical(value))<=MAX_RECORD_BYTES,'batch');return json.loads(canonical(value))


@dataclasses.dataclass(frozen=True,slots=True)
class Batch:
    batch_sha256:str
    record_bytes:bytes=dataclasses.field(repr=False)
    specs:tuple=dataclasses.field(repr=False)
    def to_record(self):
        require(type(self.record_bytes) is bytes and 0<len(self.record_bytes)<=MAX_RECORD_BYTES
            and sha(self.record_bytes)==self.batch_sha256,'batch')
        record=_metadata(self.specs);require(canonical(record)==self.record_bytes,'batch');return validate_batch_record(record)


def prepare(public_sources,addon_source_pairs,*,quote_patcher_source_bytes,common_patcher_source_bytes,
            available_source_pairs,period_source_bytes,patcher_source_bytes,expected_patcher_sha256,
            runtime_project_id,native_source_context,vendor_source_context):
    _sources(public_sources,addon_source_pairs,quote_patcher_source_bytes,common_patcher_source_bytes,
        available_source_pairs,period_source_bytes,patcher_source_bytes,expected_patcher_sha256)
    try:native_context,vendor_context=previous._contexts(runtime_project_id,native_source_context,vendor_source_context)
    except previous.Refused as error:raise Refused(previous.finite(error)) from None
    try:
        original=plain.public_specification(sources=public_sources,expected_host_source_pins={plain.HOST_SOURCE_NAME:previous.PUBLIC_SOURCE_PINS[plain.HOST_SOURCE_NAME]})
        pairs=tuple((row.project_path,row.source_bytes) for row in original.cells[0].source_files)
        quoted=quote.public_specification(pairs,patcher_source_bytes=quote_patcher_source_bytes,expected_patcher_sha256=previous.QUOTE_PATCHER_SHA256)
        quote.validate_public_projection(quoted.record_bytes,quoted.source_pairs,expected_projection_sha256=common.BASE_PROJECTION,expected_profile_sha256=common.BASE_PROFILE)
    except Exception:raise Refused('quote') from None
    available=dict(available_source_pairs)
    cloud_base=_period_base(public_sources[common.BASE_NAME],available[BASE_NAME],dict(quoted.source_pairs)[common.BASE_NAME])
    cloud_addons=tuple((name,common._cloud_source(raw,name)) for name,raw in addon_source_pairs[:-1])+(
        (BASE_NAME,cloud_base),(DRIVER_NAME,common._cloud_source(available[DRIVER_NAME],DRIVER_NAME)))
    axis=plain.bridge.frozen.october._sessions();view=period.make_period(axis)
    specs=tuple(_cell(quoted.source_pairs,cloud_addons,axis,view,size,arm,runtime_project_id,native_context,vendor_context,
        expected_patcher_sha256) for size,arm in CELL_ORDER)
    raw=canonical(_metadata(specs));require(len(raw)<=MAX_RECORD_BYTES,'batch')
    value=Batch(sha(raw),raw,specs);value.to_record();return value


def profile_record():
    return {'schema':SCHEMA,'cell_schema':CELL_SCHEMA,'cell_order':[list(value) for value in CELL_ORDER],
        'engine_start_session':ENGINE_START_SESSION,'evaluation_start_session':base.START_SESSION,
        'warmup':'two_calendar_months_callbacks_only_no_pre_evaluation_decision_orders_reference_lookups_or_NAV_observations',
        'public_source_pins':dict(previous.PUBLIC_SOURCE_PINS),'addon_source_pins':dict(previous.ADDON_SOURCE_PINS),
        'available_source_pins':dict(AVAILABLE_SOURCE_PINS),'period_source_pin':PERIOD_SOURCE_PIN,
        'frozen_quote_base_sha256':common.runtime.FROZEN_BASE_SHA256,'period_profile_sha256':period.digest(period.profile_record()),
        'source_count_per_cell':19,'source_delta':'explicit_W5_base_and_common_modules_Main_import_profile_start_date_and_declared_buy_cash_bound',
        'old_host_to_W5_host_delta':'exact_declared_byte_replacements_no_other_change',
        'W5_cloud_inverse':'exact_frozen_quote_base_AST_after_restoring_period_nodes_and_declared_cash_bound',
        'buy_cash_bound':CASH_BOUND_FIELD[1],
        'project_id':'supplied_positive_id_is_unverified_locally_not_current_cloud_authority',
        'prices':'unchanged_AR_container_native_book_codecs_source_assignments_missing_marks_stop_no_fallback',
        'CAGR':'new_Nov1_capital_epoch_calendar_days_not_old_fullperiod_result',**FALSE_FLAGS}
