"""Pure initialized-provider map trace after the isolated extended observations.

Preserves the four typed histories and all actual-child/parent/config guards.
No provider construction, initialization, fallback, mapping change, extra
history, raw aliases, prices, volumes or claimed financial recovery exists.
"""
from __future__ import annotations
import ast
import hashlib
import json

from . import comparison_20261029_project_probe as prior

PREFIX='research/target_price_revisions_qc/'
PROJECT_PROBE=PREFIX+'comparison_20261029_project_probe.py'
PINS={PROJECT_PROBE:'0d9fc4cfe89e79ec95aab5dead2c83b5f263f85b89233a771120819c4c6a505b',
    PREFIX+'comparison_20261029_extended_mark_probe.py':'0526a563426c86b2c16d1a166591e70e78d0693103057c2765f7e8e08183d867',
    PREFIX+'comparison_20261029_projects.py':'6dc87f33105de9d80e7a267a6cc737bb4262f47e49c43b65247592927a5788d7',
    PREFIX+'comparison_20261029_mark_tick_probe.py':'7bc54d85bf7e4d39a185da862934ac29bd683ab2f237fcb360919a31581f7f55',
    PREFIX+'comparison_20261028_mark_probe_post_gap_native.py':'895ee46d8c802dd707b5f85de21bf43f1e32eaf4f92f99d82f5de4e2b2b03e43',
    PREFIX+'comparison_20261028_mark_probe_post_gap.py':'bf9c69322c9fb505174908d5acd2fb4ef9ce63f458f5fcb85fea4038f77e84de',
    PREFIX+'comparison_20261028_mark_probe_control.py':'c7337090cc336472576abe4126c20317de47f31e5b9f59fb93eef36520b7662a',
    PREFIX+'comparison_20261028_mark_probe.py':'708dfff73f636d3a7f8cd4422a726e9b692d1b7ffcaab575e911db0224f7d8fc',
    PREFIX+'comparison_20261028_mark_read.py':'6539ae749aefb4884ed52258fc2f0f77c9481a5e8ee37ea80ec7065218f0da95',
    PREFIX+'comparison_20261028_algorithm.py':'27c6516b9dfd2d1e71f0ef8fbdb7c371266e36e11bd9e3089e2ce6b76d25aee0'}
SOURCE_PATHS=tuple(PINS)
DEFINITION='CMP28-INITIALIZED-MAP-TRACE-20261029-v1'
MAP_CODES=('map_configuration_unproved','map_configuration_changed','map_provider_count_unproved',
    'map_provider_type_unproved','map_resolver_type_unproved','map_file_type_unproved',
    'map_row_type_unproved','map_row_bound_or_empty','map_row_metadata_unproved',
    'map_row_order_or_conflict_unproved','map_alias_result_unproved','map_has_data_result_unproved')


class ProjectMapProbeRefusal(ValueError):pass


def _fail():raise ProjectMapProbeRefusal('source-bound initialized map diagnostic refused') from None


def _sha(raw):return hashlib.sha256(raw).hexdigest()


def _wire(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')


MAP_HELPER = '''class MapUnavailable(ValueError):
    def __init__(self,code):
        self.code=code
        super().__init__('map trace unproved')

'''

METHODS = r'''    def _map_configs(self,symbol,label):
        from QuantConnect.Data import SubscriptionDataConfig
        from QuantConnect import DataMappingMode
        cell=self._report['map_trace']
        def request():
            if cell['config_reads']>=2:raise MapUnavailable('map_configuration_unproved')
            cell['config_reads']+=1
            return self.subscription_manager.subscription_data_config_service.get_subscription_data_configs(symbol,True)
        stream=self._effect('map_cfg_'+label+'_read',request)
        cursor=self._effect('map_cfg_'+label+'_iterate',lambda:iter(stream))
        stop=object();records=[];modes=[]
        for _ in range(65):
            row=self._effect('map_cfg_'+label+'_enumerate',lambda:next(cursor,stop))
            if row is stop:break
            cell['config_rows_encountered']+=1
            if len(records)>=64:raise MapUnavailable('map_configuration_unproved')
            def inspect():
                if not isinstance(row,SubscriptionDataConfig):raise MapUnavailable('map_configuration_unproved')
                sid=str(row.symbol.id);kind=row.type.FullName;mode=row.data_mapping_mode;mapped=row.MappedSymbol
                if (sid!=str(symbol.id) or kind not in ('QuantConnect.Data.Market.TradeBar','QuantConnect.Data.Market.QuoteBar')
                        or row.resolution!=Resolution.MINUTE or row.data_normalization_mode!=DataNormalizationMode.RAW
                        or row.fill_data_forward is not False or row.extended_market_hours is not False
                        or row.is_internal_feed is not False or row.is_custom_data is not False
                        or not isinstance(mode,DataMappingMode) or type(mapped) is not str
                        or re.fullmatch(r'[A-Za-z0-9_.-]{1,64}',mapped) is None):
                    raise MapUnavailable('map_configuration_unproved')
                zones=(row.data_time_zone.Id,row.exchange_time_zone.Id)
                if any(type(zone) is not str or not 0<len(zone)<=128 for zone in zones):
                    raise MapUnavailable('map_configuration_unproved')
                token=str(mode)
                if not 0<len(token)<=64:raise MapUnavailable('map_configuration_unproved')
                frame=(sid,kind,str(row.resolution),str(row.data_normalization_mode),False,False,token,mapped,*zones)
                return frame,mode
            frame,mode=self._effect('map_cfg_'+label+'_inspect',inspect)
            records.append((frame,row))
            if frame[1]=='QuantConnect.Data.Market.TradeBar':modes.append(mode)
        if not records or len(modes)!=1:raise MapUnavailable('map_configuration_unproved')
        records.sort(key=lambda item:item[0])
        return records,modes[0]

    def _map_trace(self,symbol):
        cell={'status':'not_attempted','complete':False,'error_class':None,'provider_rows_encountered':0,
            'provider_get_calls':0,'resolve_calls':0,'map_rows_encountered':0,'mapped_symbol_calls':0,
            'has_data_calls':0,'config_reads':0,'config_rows_encountered':0,'config_before_sha256':None,
            'config_after_sha256':None,'configuration_unchanged':None,'map_rows_sha256':None,
            'sid_first_identity_matches':None,'sessions':None,'provider_initialized':False,
            'provider_constructed':False,'fallback_used':False,'alias_exported':False,'raw_map_rows_exported':False,
            'native_origin_authenticated':False,'historical_pit_authenticated':False,'financial_recovery_proven':False}
        self._report['map_trace']=cell
        try:
            before,mode=self._map_configs(symbol,'before')
            cell['config_before_sha256']=_sha(json.dumps([row[0] for row in before],sort_keys=True,separators=(',',':')).encode())
            first=None
            try:
                from QuantConnect.Interfaces import IMapFileProvider
                from QuantConnect.Util import Composer
                from QuantConnect.Data.Auxiliary import AuxiliaryDataKey,MapFileResolver,MapFile,MapFileRow
                from QuantConnect import DataMappingMode
                stream=self._effect('map_parts',lambda:Composer.Instance.GetParts[IMapFileProvider]())
                cursor=self._effect('map_parts_iter',lambda:iter(stream))
                stop=object();found=[]
                for _ in range(2):
                    item=self._effect('map_parts_next',lambda:next(cursor,stop))
                    if item is stop:break
                    cell['provider_rows_encountered']+=1;found.append(item)
                if len(found)!=1:raise MapUnavailable('map_provider_count_unproved')
                if not isinstance(found[0],IMapFileProvider):raise MapUnavailable('map_provider_type_unproved')
                def get():
                    cell['provider_get_calls']+=1
                    return found[0].Get(AuxiliaryDataKey.EquityUsa)
                resolver=self._effect('map_get',get)
                if not isinstance(resolver,MapFileResolver):raise MapUnavailable('map_resolver_type_unproved')
                def resolve():
                    cell['resolve_calls']+=1
                    return resolver.ResolveMapFile(symbol.id.Symbol,symbol.id.Date)
                mapping=self._effect('map_resolve',resolve)
                if not isinstance(mapping,MapFile):raise MapUnavailable('map_file_type_unproved')
                cursor=self._effect('map_rows_iterate',lambda:iter(mapping));rows=[];last=None;seen=set()
                for _ in range(65):
                    row=self._effect('map_rows_enumerate',lambda:next(cursor,stop))
                    if row is stop:break
                    cell['map_rows_encountered']+=1
                    if len(rows)>=64:raise MapUnavailable('map_row_bound_or_empty')
                    def inspect():
                        if not isinstance(row,MapFileRow):raise MapUnavailable('map_row_type_unproved')
                        day,alias,row_mode=row.Date,row.MappedSymbol,row.DataMappingMode
                        if (not isinstance(day,datetime) or day.time()!=time() or day.tzinfo is not None
                                or type(alias) is not str or re.fullmatch(r'[A-Za-z0-9_.-]{1,64}',alias) is None
                                or row_mode is not None and not isinstance(row_mode,DataMappingMode)):
                            raise MapUnavailable('map_row_metadata_unproved')
                        token=None if row_mode is None else str(row_mode)
                        if token is not None and not 0<len(token)<=64:raise MapUnavailable('map_row_metadata_unproved')
                        return day,alias,row_mode,token
                    item=self._effect('map_row_inspect',inspect);day,alias,row_mode,token=item
                    if last is not None and day<last or (day,token) in seen:
                        raise MapUnavailable('map_row_order_or_conflict_unproved')
                    seen.add((day,token));last=day;rows.append(item)
                if not rows:raise MapUnavailable('map_row_bound_or_empty')
                cell['map_rows_sha256']=_sha(json.dumps([(r[0].date().isoformat(),r[1],r[3]) for r in rows],separators=(',',':')).encode())
                def identity():
                    return mapping.FirstTicker==symbol.id.Symbol and mapping.FirstDate==symbol.id.Date
                cell['sid_first_identity_matches']=self._effect('map_first_identity',identity)
                dates={}
                for day in (8,9,10,11,12):
                    at=datetime(2021,2,day)
                    def mapped():
                        cell['mapped_symbol_calls']+=1
                        return mapping.GetMappedSymbol(at,'',mode)
                    alias=self._effect('map_alias',mapped)
                    def has_data():
                        cell['has_data_calls']+=1
                        return mapping.HasData(at)
                    present=self._effect('map_has_data',has_data)
                    if type(alias) is not str or alias and re.fullmatch(r'[A-Za-z0-9_.-]{1,64}',alias) is None:
                        raise MapUnavailable('map_alias_result_unproved')
                    if type(present) is not bool:raise MapUnavailable('map_has_data_result_unproved')
                    explicit=next((r[1] for r in rows if r[0]>=at and (r[2] is None or r[2]==mode)),None)
                    current=next(frame[0][7] for frame in before if frame[0][1]=='QuantConnect.Data.Market.TradeBar')
                    dates[at.date().isoformat()]={'has_data':present,'mapped_present':bool(alias),
                        'explicit_row_available':explicit is not None,'mapped_matches_explicit_row':alias==explicit if explicit is not None else None,
                        # TPR-CR33-005: no per-alias digest; sha256 of a short plain
                        # ticker is reversible, so only these comparisons leave the job.
                        'mapped_equals_current_config':alias==current if alias else None}
                cell['sessions']=dates
            except ProbeRefusal:raise
            except Exception as error:first=error
            after,after_mode=self._map_configs(symbol,'after')
            cell['config_after_sha256']=_sha(json.dumps([row[0] for row in after],sort_keys=True,separators=(',',':')).encode())
            def unchanged():
                from System import Object as NetObject
                return (mode==after_mode and [row[0] for row in before]==[row[0] for row in after]
                    and all(NetObject.ReferenceEquals(a[1],b[1]) for a,b in zip(before,after)))
            cell['configuration_unchanged']=self._effect('map_cfg_compare',unchanged)
            if not cell['configuration_unchanged']:raise MapUnavailable('map_configuration_changed')
            if first is not None:raise first
            cell.update(status='bounded_initialized_map_observations',complete=True)
        except ProbeRefusal:raise
        except Exception as error:
            cell['status']=error.code if type(error) is MapUnavailable and error.code in MAP_TRACE_CODES else 'initialized_map_api_unproved'
            cell['error_class']=next((kind.__name__ for kind in (MapUnavailable,AttributeError,TypeError,ImportError,ValueError) if type(error) is kind),'Exception')
'''


def build_project_map_probe(*,public_sources,project_bindings_raw,expected_project_bindings_sha256,operation_id,git_head):
    """Render one plain main, preserving predecessors; no private/native effect."""
    try:
        if type(public_sources) is not dict or set(public_sources)!=set(SOURCE_PATHS):_fail()
        for path,digest in PINS.items():
            raw=public_sources[path]
            if type(raw) is not bytes or _sha(raw)!=digest:_fail()
        sources={name:raw for name,raw in public_sources.items() if name!=PROJECT_PROBE}
        raw,report_raw=prior.build_project_probe(public_sources=sources,project_bindings_raw=project_bindings_raw,
            expected_project_bindings_sha256=expected_project_bindings_sha256,operation_id=operation_id,git_head=git_head)
        source=raw.decode('ascii')
        # These historical v1 entry points are never referenced by v2 custody.
        for name in ('project_witness','validate_pointer','_binding'):
            tree=ast.parse(source);nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name]
            refs=[n for n in ast.walk(tree) if isinstance(n,ast.Name) and n.id==name]
            if len(nodes)!=1 or refs:_fail()
            source=prior._replace(source,nodes[0],'')
        # Remove only nonexecuting module documentation and unreferenced URL
        # metadata. All active helper definitions remain text/AST identical.
        doc=ast.parse(source).body[0]
        if not isinstance(doc,ast.Expr) or not isinstance(doc.value,ast.Constant) or type(doc.value.value) is not str:_fail()
        source=prior._replace(source,doc,'')
        for name in ('GET_DOCUMENTATION','EXPORT_DOCUMENTATION'):
            tree=ast.parse(source)
            nodes=[n for n in tree.body if isinstance(n,ast.Assign) and len(n.targets)==1 and isinstance(n.targets[0],ast.Name) and n.targets[0].id==name]
            refs=[n for n in ast.walk(tree) if isinstance(n,ast.Name) and n.id==name and isinstance(n.ctx,ast.Load)]
            if len(nodes)!=1 or refs:_fail()
            source=prior._replace(source,nodes[0],'')
        helper_source=source[:source.index('PROBE_CONFIG_JSON = ')].encode('ascii')
        helper_definition_hash=_sha(helper_source)
        tree=ast.parse(source);main=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Main')
        source=prior._replace(source,main,MAP_HELPER+'MAP_TRACE_CODES = frozenset('+repr(MAP_CODES)+')\n\n'+source.splitlines(keepends=True)[main.lineno-1].strip()+'\n'+''.join(source.splitlines(keepends=True)[main.lineno:main.end_lineno])+ '\n'+METHODS.rstrip())
        # Remove the predecessor's separately scoped private alias export.
        label="""            # Exact native identity metadata only; separately scoped private log.
            label=self._effect('private_identity_label',lambda:symbol.value)
            if type(label) is not str or re.fullmatch(r'[A-Za-z0-9_.-]{1,64}',label) is None:
                raise ProbeRefusal('native_identity_framing_unproved')
            self._report['private_target_identity_label']=label
"""
        if source.count(label)!=1:_fail()
        source=source.replace(label,'',1)
        marker="            self._report.update(status=('completed_bounded_extended_observations'"
        if source.count(marker)!=1:_fail()
        source=source.replace(marker,"            self._map_trace(symbol)\n"+marker,1)
        source=source.replace("'schema':'tpr-cmp28-native-extended-mark-probe-result-v1'","'schema':'tpr-cmp28-native-project-map-probe-result-v1'",1)
        marker="'target_no_rows_observed_in_bound':None,'regular_session_no_trade_proven':False"
        if source.count(marker)!=1:_fail()
        source=source.replace(marker,"'map_trace':None,'alias_exported':False,"+marker,1)
        node=next(n for n in ast.parse(source).body if isinstance(n,ast.Assign) and len(n.targets)==1
            and isinstance(n.targets[0],ast.Name) and n.targets[0].id=='PROBE_CONFIG_JSON')
        config=json.loads(ast.literal_eval(node.value));config.pop('private_identity_label_max_bytes',None)
        limits=dict(max_map_config_reads=2,max_map_config_rows_each=65,max_existing_provider_rows=2,
            max_map_provider_get_calls=1,max_resolve_map_file_calls=1,max_map_rows=64,max_map_rows_encountered=65,
            max_mapped_symbol_calls=5,max_has_data_calls=5,provider_initializations=0,provider_constructions=0,
            map_trace_sessions=['2021-02-'+f'{day:02}' for day in (8,9,10,11,12)],alias_exported=False,raw_map_rows_exported=False)
        config.update(limits,schema='tpr-cmp28-native-project-map-probe-config-v1',diagnostic_definition=DEFINITION,public_source_sha256=dict(PINS))
        cfg=_wire(config);digest=_sha(cfg)
        source=prior._assignment(source,'PROBE_CONFIG_JSON',repr(cfg.decode('ascii')))
        source=prior._assignment(source,'PROBE_CONFIG_SHA256',repr(digest)).encode('ascii')
        if not 0<len(source)<=60000:_fail()
        compile(ast.parse(source),'main.py','exec')
        report=json.loads(report_raw);report.pop('private_identity_label_max_bytes',None)
        report.update(limits,schema='tpr-cmp28-project-map-probe-build-v1',diagnostic_definition=DEFINITION,
            public_source_sha256=dict(PINS),config_sha256=digest,main_sha256=_sha(source),main_bytes=len(source),
            map_trace_after_existing_four_histories=True,initialized_provider_only=True,financial_recovery_proven=False,
            native_routing_fix_proven=False,provider_hole_excluded=False,independent_native_origin_attested=False,
            original_helper_source_sha256=PINS[PREFIX+'comparison_20261028_mark_read.py'],
            rendered_helper_definition_sha256=helper_definition_hash,rendered_helper_definition_bytes=len(helper_source),
            full_original_helper_bytes_preserved=False,
            additional_map_source_edits=['Main._map_cfg_private_before_after','Main._map_trace_initialized_provider',
                'remove_private_alias_export','source_select_remove_unreferenced_v1_witness_entrypoints',
                'remove_nonexecuting_helper_module_doc_and_unreferenced_documentation_urls'])
        return source,_wire(report)+b'\n'
    except ProjectMapProbeRefusal:raise
    except Exception:_fail()
