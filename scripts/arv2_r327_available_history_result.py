"""Pure selected terminal boundary for the common-price aggregate result.

The operational caller must independently bind the exact project, source
readback, compile, launch, job and actual terminal to its frozen one-shot run.
This helper reads no files or services. An external selected-byte pin covers
only the closed projection below, never ignored QC charts, orders or trades.
"""
import hashlib
import json
import re

from research.analyst_revisions_v2_qc import newrule_available_history_common_price_runtime as runtime
from scripts import arv2_r327_available_history_period as period
from scripts import arv2_r327_available_history_projection as projection

SCHEMA = 'arv2-r327-available-history-selected-result-v1'
FAMILY_SCHEMA = SCHEMA + '-six-cell-family'
PERIOD_SHA256 = '88113155d49f74e00a89ba743aaa314d718cfd0d29b017ac501058460fe5d11a'
ENGINE_START_SESSION = '2021-09-01'
BATCH_SCHEMA = 'arv2-r327-available-history-public-batch-v1'
MAX_BATCH_BYTES = 131072
LAUNCH_SCHEMA = SCHEMA + '-launch-binding'
MAX_SELECTED_BYTES, MAX_STATISTIC_BYTES, MAX_LAUNCH_BYTES = 65536, 16384, 4096
BINDING_KEYS = frozenset(('project_id', 'backtest_id', 'name', 'compile_id',
    'source_manifest_sha256', 'common_profile_sha256', 'run_scope_tag',
    'research_epoch_id', 'period_sha256', 'universe_count', 'ar_percent',
    'public_batch_sha256', 'projection_sha256'))
SELECTED_KEYS = frozenset(('schema', 'binding', 'terminal', 'response_success', 'response_error_count', 'response_compile_id',
    'compile_binding_source', 'launch_binding_pin', 'statistics', 'aggregate_sha256',
    'aggregate_schema_checks_passed', 'selection_pin_scope', *(
        'whole_response_authenticated', 'source_job_authenticated_by_pure_helper',
        'strategy_result_accepted', 'source_admission_granted', 'point_in_time_proven',
        'formal_identity_admitted', 'formal_forward_ready', 'paper_or_live_ready', 'full_2021_study_reproduced', 'QC_or_Safari_access_performed')))
FALSE_FLAGS = {'whole_response_authenticated': False, 'source_job_authenticated_by_pure_helper': False,
    'full_2021_study_reproduced': False, 'QC_or_Safari_access_performed': False,
    'strategy_result_accepted': False, 'source_admission_granted': False, 'point_in_time_proven': False,
    'formal_identity_admitted': False, 'formal_forward_ready': False, 'paper_or_live_ready': False}
FINITE = frozenset(('binding', 'profile', 'profile_binding', 'response', 'response_success',
    'response_errors', 'response_identity', 'response_terminal', 'response_compile',
    'launch_required', 'launch_bound', 'launch_pin', 'launch_shape', 'launch_binding',
    'statistics', 'aggregate', 'selected_bound', 'selected_pin', 'selected_shape',
    'selected_binding', 'actual_exit', 'json', 'public_cell', 'batch', 'family', 'family_scope',
    'family_jobs', 'family_economics', 'unknown'))


class Refused(ValueError):
    """Finite protocol predicate; never response rows, identifiers or errors."""


def require(value, code):
    if not value: raise Refused(code)


def finite(error):
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
        allow_nan=False).encode('ascii')


def sha(raw): return hashlib.sha256(raw).hexdigest()


def _hash(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def _identifier(value):
    return type(value) is str and re.fullmatch('[A-Za-z0-9_-]{1,128}', value) is not None


def _pin(value, maximum, code):
    require(type(value) is dict and set(value) == {'byte_count', 'sha256'}
        and type(value['byte_count']) is int and 0 < value['byte_count'] <= maximum
        and _hash(value['sha256']), code)
    return {'byte_count': value['byte_count'], 'sha256': value['sha256']}


def _bytes_pin(raw):
    return {'byte_count': len(raw), 'sha256': sha(raw)}


def _loads(raw, maximum, code):
    require(type(raw) is bytes and 0 < len(raw) <= maximum, code)
    def pairs(items):
        value = {}
        for name, child in items:
            require(name not in value, 'json')
            value[name] = child
        return value
    try:
        value = json.loads(raw.decode('ascii'), object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(Refused('json')))
        require(canonical(value) == raw, 'json')
        return value
    except Refused:
        raise
    except (UnicodeError, ValueError, TypeError, RecursionError):
        raise Refused('json') from None


def validate_run_binding(value, *, expected_profile, expected_public_cell):
    require(type(value) is dict and set(value) == BINDING_KEYS
        and type(value['project_id']) is int and 0 < value['project_id'] <= 2147483647
        and type(value['backtest_id']) is str and re.fullmatch('[0-9a-f]{32}', value['backtest_id']) is not None
        and _identifier(value['compile_id']) and _identifier(value['run_scope_tag'])
        and type(value['name']) is str and 0 < len(value['name']) <= 200
        and value['name'].isascii() and all(32 <= ord(char) < 127 for char in value['name'])
        and _hash(value['source_manifest_sha256']) and _hash(value['common_profile_sha256'])
        and type(value['research_epoch_id']) is str and value['research_epoch_id'] == period.RESEARCH_EPOCH_ID
        and value['period_sha256'] == PERIOD_SHA256 and type(value['universe_count']) is int and value['universe_count'] in (6, 8)
        and type(value['ar_percent']) is int and value['ar_percent'] in (0, 100, 200)
        and _hash(value['public_batch_sha256']) and _hash(value['projection_sha256']), 'binding')
    try:
        profile = runtime.validate_profile(expected_profile)
    except Exception:
        raise Refused('profile') from None
    require(value['project_id'] == profile['runtime_project_id']
        and value['common_profile_sha256'] == profile['profile_sha256']
        and value['research_epoch_id'] == profile['research_epoch_id']
        and value['universe_count'] == profile['universe_count'] and value['ar_percent'] == profile['ar_percent'], 'profile_binding')
    _cell_binding(expected_public_cell, value, profile)
    return dict(value)


def _launch(raw, expected_pin, binding):
    if raw is None and expected_pin is None:
        return None
    require(raw is not None and expected_pin is not None, 'launch_pin')
    pin = _pin(expected_pin, MAX_LAUNCH_BYTES, 'launch_pin')
    require(type(raw) is bytes and 0 < len(raw) <= MAX_LAUNCH_BYTES, 'launch_bound')
    require(_bytes_pin(raw) == pin, 'launch_pin')
    value = _loads(raw, MAX_LAUNCH_BYTES, 'launch_bound')
    require(type(value) is dict and set(value) == {'schema', 'binding'}
        and value['schema'] == LAUNCH_SCHEMA, 'launch_shape')
    require(type(value['binding']) is dict and set(value['binding']) == BINDING_KEYS
        and all(type(value['binding'][key]) is type(binding[key]) and value['binding'][key] == binding[key]
            for key in BINDING_KEYS), 'launch_binding')
    return pin


def _compile(response_compile_id, launch_binding_bytes, expected_launch_binding_pin, binding):
    require(response_compile_id is None or _identifier(response_compile_id)
        and response_compile_id == binding['compile_id'], 'response_compile')
    launch_pin = _launch(launch_binding_bytes, expected_launch_binding_pin, binding)
    require(response_compile_id is not None or launch_pin is not None, 'launch_required')
    source = ('response_and_launch' if launch_pin is not None else 'response_only') if response_compile_id is not None else 'launch_only'
    return source, launch_pin


def _statistics(value, expected_profile):
    require(type(value) is dict, 'statistics')
    selected = {}
    for name in (runtime.META_STATISTIC, runtime.MONTHLY_STATISTIC):
        text = value.get(name)
        require(type(text) is str and 0 < len(text) <= MAX_STATISTIC_BYTES and text.isascii(), 'statistics')
        selected[name] = text
    try:
        aggregate = runtime.validate_result_statistics(selected, expected_profile=expected_profile)
    except Exception:
        raise Refused('aggregate') from None
    return selected, aggregate


def select_response(value, *, expected_run_binding, expected_profile, expected_public_cell,
                    launch_binding_bytes=None, expected_launch_binding_pin=None):
    """Select only two genuine aggregate statistics from an already decoded reply.

    A missing response compileId requires supplied closed launch-binding bytes
    and their separately frozen external pin. Neither a boolean nor a generated
    compile identifier is accepted. External authentication remains the caller's
    responsibility; this pure comparison grants no authority.
    """
    binding = validate_run_binding(expected_run_binding, expected_profile=expected_profile, expected_public_cell=expected_public_cell)
    require(type(value) is dict, 'response')
    require(value.get('success') is True, 'response_success')
    require(type(value.get('errors')) is list and not value['errors'], 'response_errors')
    row = value.get('backtest')
    require(type(row) is dict, 'response_identity')
    require(type(row.get('projectId')) is int and row['projectId'] == binding['project_id']
        and type(row.get('backtestId')) is str and row['backtestId'] == binding['backtest_id']
        and type(row.get('name')) is str and row['name'] == binding['name'], 'response_identity')
    require(type(row.get('status')) is str and row['status'] == 'Completed.', 'response_terminal')
    response_compile_id = row.get('compileId')
    if 'compileId' in row:
        require(_identifier(response_compile_id) and response_compile_id == binding['compile_id'], 'response_compile')
    compile_source, launch_pin = _compile(response_compile_id, launch_binding_bytes, expected_launch_binding_pin, binding)
    statistics, aggregate = _statistics(row.get('statistics'), expected_profile)
    selected = {'schema': SCHEMA, 'binding': binding, 'terminal': 'Completed.',
        'response_success': True, 'response_error_count': 0,
        'response_compile_id': response_compile_id, 'compile_binding_source': compile_source,
        'launch_binding_pin': launch_pin, 'statistics': statistics, 'aggregate_sha256': sha(canonical(aggregate)),
        'aggregate_schema_checks_passed': True, 'selection_pin_scope': 'selected_projection_only', **FALSE_FLAGS}
    raw = canonical(selected)
    require(0 < len(raw) <= MAX_SELECTED_BYTES, 'selected_bound')
    return selected, _bytes_pin(raw)


def validate_selected(raw, *, expected_selected_pin, expected_run_binding, expected_profile, expected_public_cell,
                      actual_reader_exit, launch_binding_bytes=None, expected_launch_binding_pin=None):
    """Accept exact pinned selected bytes only after an observed real reader exit0."""
    require(type(actual_reader_exit) is int and actual_reader_exit == 0, 'actual_exit')
    binding = validate_run_binding(expected_run_binding, expected_profile=expected_profile, expected_public_cell=expected_public_cell)
    pin = _pin(expected_selected_pin, MAX_SELECTED_BYTES, 'selected_pin')
    require(type(raw) is bytes and 0 < len(raw) <= MAX_SELECTED_BYTES, 'selected_bound')
    require(_bytes_pin(raw) == pin, 'selected_pin')
    value = _loads(raw, MAX_SELECTED_BYTES, 'selected_bound')
    require(type(value) is dict and set(value) == SELECTED_KEYS and value['schema'] == SCHEMA
        and value['terminal'] == 'Completed.' and value['response_success'] is True
        and type(value['response_error_count']) is int and value['response_error_count'] == 0
        and value['aggregate_schema_checks_passed'] is True
        and value['selection_pin_scope'] == 'selected_projection_only'
        and all(value[key] is False for key in FALSE_FLAGS), 'selected_shape')
    require(type(value['binding']) is dict and set(value['binding']) == BINDING_KEYS
        and all(type(value['binding'][key]) is type(binding[key]) and value['binding'][key] == binding[key]
            for key in BINDING_KEYS), 'selected_binding')
    compile_source, launch_pin = _compile(value['response_compile_id'], launch_binding_bytes,
        expected_launch_binding_pin, binding)
    require(value['compile_binding_source'] == compile_source and value['launch_binding_pin'] == launch_pin,
        'selected_binding')
    require(type(value['statistics']) is dict and set(value['statistics']) == {
        runtime.META_STATISTIC, runtime.MONTHLY_STATISTIC}, 'statistics')
    statistics, aggregate = _statistics(value['statistics'], expected_profile)
    require(value['aggregate_sha256'] == sha(canonical(aggregate)), 'aggregate')
    return {'selected': value, 'selected_pin': pin, 'aggregate': aggregate}



CELL_KEYS = frozenset(('universe_count','ar_percent','candidate_id','common_profile_sha256',
    'strategy_profile_sha256','profile_pin','projection_pin','projection_sha256','source_manifest_pin',
    'main_pin','source_file_count','source_files'))


def _cell_binding(value, binding, profile):
    """Join supplied public source metadata, never claim cloud source readback."""
    require(type(value) is dict and set(value)==CELL_KEYS,'public_cell')
    for name in ('profile_pin','projection_pin','source_manifest_pin','main_pin'):
        _pin(value[name],MAX_BATCH_BYTES,'public_cell')
    require(type(value['universe_count']) is type(value['ar_percent']) is int
        and value['universe_count']==binding['universe_count'] and value['ar_percent']==binding['ar_percent']
        and value['candidate_id']==profile['candidate_id']
        and value['common_profile_sha256']==profile['profile_sha256']
        and value['strategy_profile_sha256']==profile['strategy_profile_sha256']
        and value['projection_sha256']==binding['projection_sha256']
        and value['projection_pin']['sha256']==binding['projection_sha256']
        and value['profile_pin']==_bytes_pin(canonical(profile))
        and value['source_manifest_pin']['sha256']==binding['source_manifest_sha256']
        and type(value['source_file_count']) is int and value['source_file_count']==19
        and type(value['source_files']) is list and len(value['source_files'])==19,'public_cell')
    names=[]
    for row in value['source_files']:
        require(type(row) is dict and set(row)=={'project_path','byte_count','content_sha256'}
            and type(row['project_path']) is str and re.fullmatch('[A-Za-z0-9_]+\\.py',row['project_path'])
            and type(row['byte_count']) is int and 0<row['byte_count']<=projection.MAX_SOURCE_BYTES
            and _hash(row['content_sha256']),'public_cell')
        names.append(row['project_path'])
        if row['project_path']!='main.py':
            require(profile['source_pins'].get(row['project_path'])==row['content_sha256'],'public_cell')
    require(len(set(names))==19 and names.count('main.py')==1,'public_cell')
    main=next(row for row in value['source_files'] if row['project_path']=='main.py')
    require(value['main_pin']=={'byte_count':main['byte_count'],'sha256':main['content_sha256']},'public_cell')
    manifest={'schema':BATCH_SCHEMA+'-source-manifest','runtime_project_id':binding['project_id'],
        'profile_sha256':profile['profile_sha256'],'source_files':value['source_files']}
    require(value['source_manifest_pin']==_bytes_pin(canonical(manifest)),'public_cell')


def _shared_profile(profile):
    strategy=dict(profile['strategy_profile'])
    for key in ('candidate_id','universe_count','ar_percent','profile_sha256'):strategy.pop(key)
    common=dict(profile)
    for key in ('candidate_id','universe_count','ar_percent','profile_sha256','strategy_profile','strategy_profile_sha256'):
        common.pop(key)
    return {'common':common,'strategy':strategy,
        'declared_economics_policy_sha256':period.digest(period.economics_policy()),
        'declared_original_source_policy_sha256':period.digest(period.source_policy())}


def validate_family(entries, *, expected_batch_bytes, expected_batch_pin,
                    expected_run_bindings, expected_profiles, actual_family_reader_exit):
    """Join six individually observed/pinned results without granting acceptance.

    External execution owns actual job/source/reader provenance. This helper
    checks the exact selected projections only; no response chart, order, trade,
    service, artifact, credential or current cloud state is accessed.
    """
    require(type(actual_family_reader_exit) is int and actual_family_reader_exit==0,'actual_exit')
    batch_pin=_pin(expected_batch_pin,MAX_BATCH_BYTES,'batch')
    require(type(expected_batch_bytes) is bytes and _bytes_pin(expected_batch_bytes)==batch_pin,'batch')
    batch=_loads(expected_batch_bytes,MAX_BATCH_BYTES,'batch')
    try:batch=projection.validate_batch_record(batch)
    except Exception:raise Refused('batch') from None
    require(batch['schema']==BATCH_SCHEMA and batch['period_sha256']==PERIOD_SHA256
        and batch['research_epoch_id']==period.RESEARCH_EPOCH_ID
        and batch['engine_start_session']==ENGINE_START_SESSION
        and batch['evaluation_first']==runtime.START_SESSION and batch['evaluation_last']==runtime.END_SESSION
        and batch['first_reference_close']==period.PRIOR
        and type(entries) in (tuple,list) and len(entries)==6
        and type(expected_run_bindings) in (tuple,list) and len(expected_run_bindings)==6
        and type(expected_profiles) in (tuple,list) and len(expected_profiles)==6,'family')
    shared=None;checked=[];jobs=set();compiles=set();names=set();tags=set();sources=set()
    resolutions=set();translations=set()
    for index,(size,arm) in enumerate(period.CELLS):
        entry=entries[index]
        require(type(entry) is dict and set(entry)=={'selected_bytes','selected_pin','actual_reader_exit',
            'launch_binding_bytes','expected_launch_binding_pin'},'family')
        binding=validate_run_binding(expected_run_bindings[index],expected_profile=expected_profiles[index],
            expected_public_cell=batch['cells'][index])
        require((binding['universe_count'],binding['ar_percent'])==(size,arm)
            and binding['project_id']==batch['runtime_project_id']
            and binding['public_batch_sha256']==batch_pin['sha256'],'family_scope')
        profile=runtime.validate_profile(expected_profiles[index])
        require(profile['native_source_context_sha256']==batch['native_source_context_sha256']
            and profile['vendor_source_context_sha256']==batch['vendor_source_context_sha256'],'family_scope')
        current=_shared_profile(profile)
        if shared is None:shared=current
        else:require(current==shared,'family_economics')
        result=validate_selected(entry['selected_bytes'],expected_selected_pin=entry['selected_pin'],
            expected_run_binding=binding,expected_profile=profile,expected_public_cell=batch['cells'][index],
            actual_reader_exit=entry['actual_reader_exit'],launch_binding_bytes=entry['launch_binding_bytes'],
            expected_launch_binding_pin=entry['expected_launch_binding_pin'])
        for collection,value in ((jobs,binding['backtest_id']),(compiles,binding['compile_id']),
                (names,binding['name']),(tags,binding['run_scope_tag']),(sources,binding['source_manifest_sha256'])):
            require(value not in collection,'family_jobs');collection.add(value)
        common=result['aggregate']['meta']['common_price']
        resolutions.add(common['fresh_resolution_sha256']);translations.add(common['fund_translation_sha256'])
        checked.append(result)
    require(len(resolutions)==len(translations)==1,'family_scope')
    family={'schema':FAMILY_SCHEMA,'public_batch_pin':batch_pin,'runtime_project_id':batch['runtime_project_id'],
        'research_epoch_id':period.RESEARCH_EPOCH_ID,'period_sha256':PERIOD_SHA256,
        'engine_start_session':ENGINE_START_SESSION,'evaluation_first':batch['evaluation_first'],
        'evaluation_last':batch['evaluation_last'],'first_reference_close':batch['first_reference_close'],
        'performance_metric_scope':'custom_Nov1_capital_epoch_only_not_QC_engine_warmup_period',
        'cell_order':[list(cell) for cell in period.CELLS],'cell_count':6,'technical_selected_results_complete':True,
        'shared_source_and_economics_sha256':sha(canonical(shared)),
        'fresh_resolution_sha256':next(iter(resolutions)),'fund_translation_sha256':next(iter(translations)),
        'cells':[{'universe_count':period.CELLS[index][0],'ar_percent':period.CELLS[index][1],
            'binding':result['selected']['binding'],'selected_pin':result['selected_pin'],
            'aggregate_sha256':result['selected']['aggregate_sha256']} for index,result in enumerate(checked)],
        **FALSE_FLAGS}
    return {'family':family,'family_pin':_bytes_pin(canonical(family)),'results':tuple(checked)}


def profile_record():
    return {'schema': SCHEMA, 'binding_fields': sorted(BINDING_KEYS), 'launch_schema': LAUNCH_SCHEMA,
        'terminal': 'Completed.', 'maximum_selected_bytes': MAX_SELECTED_BYTES,
        'family_schema':FAMILY_SCHEMA,'period_sha256':PERIOD_SHA256,'research_epoch_id':period.RESEARCH_EPOCH_ID,
        'engine_start_session':ENGINE_START_SESSION,'evaluation_first':runtime.START_SESSION,
        'evaluation_last':runtime.END_SESSION,'first_reference_close':period.PRIOR,
        'performance_metric_scope':'custom_Nov1_capital_epoch_only_not_QC_engine_warmup_period',
        'cell_order':[list(cell) for cell in period.CELLS],
        'family_binding':'external_exact_public_batch_pin_plus_six_unique_jobs_compiles_names_scope_tags_source_manifests_on_one_project',
        'same_project_for_six_cells':True,'shared_economics_and_source_profiles_checked':True,
        'new_W5_profile_schema':runtime.SCHEMA,'new_W5_result_schema':runtime.RESULT_SCHEMA,'new_W5_month_schema':runtime.MONTH_SCHEMA,
        'maximum_statistic_bytes_each': MAX_STATISTIC_BYTES, 'maximum_launch_bytes': MAX_LAUNCH_BYTES,
        'statistics': [runtime.META_STATISTIC, runtime.MONTHLY_STATISTIC],
        'compile_absence': 'closed_supplied_launch_binding_bytes_and_separately_frozen_external_pin',
        'selected_authentication': 'observed_actual_reader_exit0_and_external_exact_selected_bytes_pin',
        'ignored_subtrees': 'never_traversed_canonicalized_hashed_or_retained',
        'external_prerequisites': 'exact_project_source_readback_compile_launch_job_profile_terminal_and_one_shot_protocol',
        **FALSE_FLAGS}
