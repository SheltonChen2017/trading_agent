"""Pure two-call, same-SID closing-minute Tick availability diagnostic.

All six reviewed public predecessors are pinned and preserved. The generated
plaintext main reads the one known parent witness, independently binds its
actual research child job, and requests one fixed minute for SPY and the exact
parent SID. Mixed Tick types are counted, never mistaken for trade prices.
No bar, cache update, financial recovery, entitlement or native effect here.
"""
from __future__ import annotations

import ast
import hashlib
import json

from . import comparison_20261028_mark_probe_post_gap_native as prior

PINS = {
    'native_post_gap_source':'895ee46d8c802dd707b5f85de21bf43f1e32eaf4f92f99d82f5de4e2b2b03e43',
    'post_gap_source':'bf9c69322c9fb505174908d5acd2fb4ef9ce63f458f5fcb85fea4038f77e84de',
    'control_source':'c7337090cc336472576abe4126c20317de47f31e5b9f59fb93eef36520b7662a',
    'base_probe_source':'708dfff73f636d3a7f8cd4422a726e9b692d1b7ffcaab575e911db0224f7d8fc',
    'helper_source':'6539ae749aefb4884ed52258fc2f0f77c9481a5e8ee37ea80ec7065218f0da95',
    'producer_source':'27c6516b9dfd2d1e71f0ef8fbdb7c371266e36e11bd9e3089e2ce6b76d25aee0',
}
DEFINITION = 'CMP28-NATIVE-TICK-CLOSE-20261029-v1'
CODES = ('tick_history_scope_unproved','tick_row_type_unproved','tick_identity_or_fillforward_unproved',
    'tick_time_unproved','tick_outside_request','tick_order_unproved','tick_type_unproved',
    'tick_source_flag_unproved','tick_suspicious_unproved','tick_trade_price_or_quantity_unproved')


class TickProbeBuildRefusal(ValueError):
    """Body-free invalid public source or closed native diagnostic definition."""


def _fail():
    raise TickProbeBuildRefusal('fixed native tick diagnostic build refused') from None


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


HISTORY = r'''    def _history(self,symbol,start,end,label):
        if (type(label) is not str or label not in ('control_ticks','target_ticks')
                or type(start) is not datetime or start!=datetime(2021,2,10,15,59)
                or type(end) is not datetime or end!=datetime(2021,2,10,16,0)):
            raise ProbeRefusal('tick_history_scope_unproved')
        cell={'status':'unattempted','request_attempted':False,'request_returned':False,
            'rows_encountered':0,'rows_validated':0,'trade_rows':0,'quote_rows':0,
            'unknown_type_rows':0,'invalid_row_rows':0,'invalid_source_flag_rows':0,
            'suspicious_rows':0,'final_minute_trade_rows':0,'close_boundary_trade_rows':0,
            'complete':False,'row_bound_reached_result_may_be_incomplete':False,
            'quote_price_consumed':False,'price_or_quantity_exported':False}
        self._report[label]=cell
        def request():
            if self._report['history_calls']>=2:raise ProbeRefusal('history_call_bound')
            self._report['history_calls']+=1;cell['request_attempted']=True;cell['status']='request_in_progress'
            method=self.history[Tick]
            return method(symbol,start,end,Resolution.TICK,fill_forward=False,extended_market_hours=False,
                data_normalization_mode=DataNormalizationMode.RAW)
        try:
            stream=self._effect('history_'+label+'_request',request)
            cell['request_returned']=True;cell['status']='enumeration_in_progress'
            iterator=self._effect('history_'+label+'_iterate',lambda:iter(stream))
            sentinel=object();previous=None
            for _ in range(50000):
                row=self._effect('history_'+label+'_enumerate',lambda:next(iterator,sentinel))
                if row is sentinel:
                    cell.update(status='complete_bounded_observation',complete=True)
                    break
                # Count EVERY source row before any classification or refusal.
                cell['rows_encountered']+=1;self._report['tick_rows_encountered']+=1
                if self._report['tick_rows_encountered']>100000:
                    raise ProbeRefusal('history_call_bound')
                def inspect():
                    if not isinstance(row,Tick):
                        cell['invalid_row_rows']+=1;raise ProbeRefusal('tick_row_type_unproved')
                    if row.symbol.id!=symbol.id or row.is_fill_forward is not False:
                        cell['invalid_row_rows']+=1;raise ProbeRefusal('tick_identity_or_fillforward_unproved')
                    stamp,ended=row.time,row.end_time
                    if not isinstance(stamp,datetime) or not isinstance(ended,datetime):
                        cell['invalid_row_rows']+=1;raise ProbeRefusal('tick_time_unproved')
                    stamp=stamp.replace(tzinfo=NY) if stamp.tzinfo is None else stamp.astimezone(NY)
                    ended=ended.replace(tzinfo=NY) if ended.tzinfo is None else ended.astimezone(NY)
                    if stamp!=ended or stamp.date()!=date(2021,2,10) or not start.replace(tzinfo=NY)<=stamp<=end.replace(tzinfo=NY):
                        cell['invalid_row_rows']+=1;raise ProbeRefusal('tick_outside_request')
                    if previous is not None and stamp<previous:
                        cell['invalid_row_rows']+=1;raise ProbeRefusal('tick_order_unproved')
                    kind=row.tick_type
                    if kind not in (TickType.TRADE,TickType.QUOTE):
                        cell['unknown_type_rows']+=1;raise ProbeRefusal('tick_type_unproved')
                    if type(row.suspicious) is not bool:
                        cell['invalid_source_flag_rows']+=1;raise ProbeRefusal('tick_source_flag_unproved')
                    if row.suspicious is True:
                        cell['suspicious_rows']+=1;raise ProbeRefusal('tick_suspicious_unproved')
                    if kind==TickType.TRADE:
                        try:
                            _probe_number(row.last_price);_probe_number(row.quantity)
                        except Exception:
                            cell['invalid_row_rows']+=1;raise ProbeRefusal('tick_trade_price_or_quantity_unproved') from None
                    # A Quote row never exposes/reads its value, price or quantity.
                    return stamp,kind,stamp==end.replace(tzinfo=NY)
                previous,kind,boundary=self._effect('history_'+label+'_inspect',inspect)
                cell['rows_validated']+=1
                if kind==TickType.TRADE:
                    cell['trade_rows']+=1
                    cell['close_boundary_trade_rows' if boundary else 'final_minute_trade_rows']+=1
                else:cell['quote_rows']+=1
            else:
                cell.update(status='row_bound_incomplete',row_bound_reached_result_may_be_incomplete=True)
        except BaseException:
            if cell['status'] in ('request_in_progress','enumeration_in_progress'):
                cell['status']='access_or_validation_unproved'
            raise
'''

QUERY = '''            start=datetime(2021,2,10,15,59)
            end=datetime(2021,2,10,16,0)
            self._history(self._clock,start,end,'control_ticks')
            control=self._report['control_ticks']
            positive=control['trade_rows']>0
            self._report['control_request_path_status']='positive_trade_ticks_observed' if positive else 'request_path_unproved'
            self._register_parent(symbol)
            self._history(symbol,start,end,'target_ticks')
            target=self._report['target_ticks']
            self._report['target_trade_ticks_observed']=target['trade_rows']>0
            complete=control['complete'] and target['complete']
            self._report['target_no_trade_ticks_observed_in_bound']=(target['trade_rows']==0) if complete and positive else None
            self._report.update(status=('completed_bounded_tick_observations' if positive and complete else
                'tick_row_bound_incomplete' if not complete else 'request_path_unproved'),phase='complete')'''


def build_mark_tick_probe(*, native_post_gap_source, post_gap_source, control_source,
        base_probe_source, helper_source, producer_source, operation_id, git_head):
    """Render main/report from exact public bytes only; external claims required."""
    supplied=dict(native_post_gap_source=native_post_gap_source,post_gap_source=post_gap_source,
        control_source=control_source,base_probe_source=base_probe_source,helper_source=helper_source,
        producer_source=producer_source)
    if any(type(raw) is not bytes or _sha(raw)!=PINS[name] for name,raw in supplied.items()):_fail()
    try:
        raw,report_raw=prior.build_mark_probe_post_gap_native(**{name:value for name,value in supplied.items()
            if name!='native_post_gap_source'},operation_id=operation_id,git_head=git_head)
        source=raw.decode('utf-8');control=prior.prior.control
        def method(name):
            main=next(node for node in ast.parse(source).body if isinstance(node,ast.ClassDef) and node.name=='Main')
            found=[node for node in main.body if isinstance(node,ast.FunctionDef) and node.name==name]
            if len(found)!=1:_fail()
            return found[0]
        source=control._replace_node(source,method('_session_windows'),'')
        source=control._replace_node(source,method('_history'),HISTORY[4:])
        original=prior.prior.QUERY_BLOCK.replace('end=self.time.replace(tzinfo=None)','end=datetime(2021,2,12,16,1)')
        source=control._replace_once(source,original,QUERY)
        source=control._replace_once(source,"'post_gap_runtime_clock_unproved'))",
            "'post_gap_runtime_clock_unproved',"+','.join(repr(code) for code in CODES)+"))")
        source=control._replace_once(source,"'schema':'tpr-cmp28-native-mark-probe-post-gap-native-result-v1'",
            "'schema':'tpr-cmp28-native-mark-tick-probe-result-v1'")
        source=control._replace_once(source,"'diagnostic_only_no_financial_recovery':True,'native_regular_calendars':{'control':None,'target':None},\n            'target_post_failure_rows_observed':None,",
            "'diagnostic_only_no_financial_recovery':True,'control_ticks':None,'target_ticks':None,\n            'tick_rows_encountered':0,'target_trade_ticks_observed':None,'target_no_trade_ticks_observed_in_bound':None,\n            'mixed_trade_quote_request':True,'native_clock_class_attested':False,'native_origin_authenticated':False,\n            'point_in_time_verified':False,'rights_verified':False,'financial_recovery_proven':False,\n            'cache_updated':False,'derived_bar_created':False,'orders_submitted':0,'cash_changes_made':False,\n            'sdk_hard_timeout_proven':False,'sdk_preallocation_byte_bound_proven':False,\n            'external_manifest_attested':False,'external_operation_manifest_required':True,\n            'one_of_five_economic_arms':False,'native_permission':False,'orders_authorized':False,'trading_authority':False,")
        # Freeze the decoded parent/key scope at setup and recheck it before all
        # existing actual-job/clock guards; JSON relabelling grants no custody.
        source=control._replace_once(source,"        self._phase = 'initialize'",
            "        self._tick_config_json=PROBE_CONFIG_JSON;self._tick_config_sha256=PROBE_CONFIG_SHA256\n        self._phase = 'initialize'")
        bound=method('_bound');lines=source.splitlines(keepends=True)
        body=''.join(lines[bound.lineno-1:bound.end_lineno])[4:]
        identity="""        if (type(PROBE_CONFIG_JSON) is not str or type(PROBE_CONFIG_SHA256) is not str
                or PROBE_CONFIG_JSON!=self._tick_config_json or PROBE_CONFIG_SHA256!=self._tick_config_sha256
                or _sha(PROBE_CONFIG_JSON.encode('ascii'))!=self._tick_config_sha256
                or type(PROBE_CONFIG) is not dict or json.dumps(PROBE_CONFIG,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)!=PROBE_CONFIG_JSON):
            raise ProbeRefusal('config_digest')
"""
        checked=body.replace('def _bound(self):\n','def _bound(self):\n        self._tick_config_bound()\n',1).rstrip()+'\n        self._tick_config_bound()'
        source=control._replace_node(source,bound,'def _tick_config_bound(self):\n'+identity+'\n    '+checked)
        config_node=next(node for node in ast.parse(source).body if isinstance(node,ast.Assign) and len(node.targets)==1
            and isinstance(node.targets[0],ast.Name) and node.targets[0].id=='PROBE_CONFIG_JSON')
        config=json.loads(ast.literal_eval(config_node.value))
        for key in ('allowed_failure_date_offsets','max_minute_rows','max_daily_rows',
                'max_native_calendar_sessions_per_symbol','max_native_market_hours_calls'):
            config.pop(key,None)
        config.update(schema='tpr-cmp28-native-mark-tick-probe-config-v1',diagnostic_definition=DEFINITION,
            public_source_sha256=dict(PINS),history_start_local='2021-02-10T15:59:00',history_end_local='2021-02-10T16:00:00',
            history_start_session='2021-02-10',request_endpoint_construction='fixed_plain_datetime_tick_endpoints_v1',
            max_history_calls=2,max_tick_rows_per_symbol=50000,max_total_tick_rows=100000,max_native_market_hours_calls=0,
            mixed_trade_quote_request=True,quote_prices_consumed=False,derived_bar_created=False,cache_updated=False,
            sdk_hard_timeout_proven=False,sdk_preallocation_byte_bound_proven=False)
        config_raw=json.dumps(config,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')
        digest=_sha(config_raw)
        source=control._assignment(source,'PROBE_CONFIG_JSON',repr(config_raw.decode('ascii')))
        source=control._assignment(source,'PROBE_CONFIG_SHA256',repr(digest)).encode('utf-8')
        if not 0<len(source)<=60000:_fail()
        compile(ast.parse(source),'main.py','exec')
        report=json.loads(report_raw)
        for key in ('allowed_failure_date_offsets','max_minute_rows','max_daily_rows','max_minute_rows_per_symbol',
                'max_daily_rows_per_symbol','max_total_history_rows','max_native_calendar_sessions_per_symbol'):
            report.pop(key,None)
        report.update(schema='tpr-cmp28-mark-tick-probe-build-v1',diagnostic_definition=DEFINITION,
            public_source_sha256=dict(PINS),config_sha256=digest,main_sha256=_sha(source),main_bytes=len(source),
            history_start_session='2021-02-10',history_start_local='2021-02-10T15:59:00',history_end_local='2021-02-10T16:00:00',
            request_endpoint_construction='fixed_plain_datetime_tick_endpoints_v1',max_history_calls=2,
            max_tick_rows_per_symbol=50000,max_total_tick_rows=100000,max_native_market_hours_calls=0,
            mixed_trade_quote_request=True,quote_prices_consumed=False,derived_bar_created=False,cache_updated=False,
            sdk_hard_timeout_proven=False,sdk_preallocation_byte_bound_proven=False,
            native_origin_authenticated=False,point_in_time_verified=False,rights_verified=False,canonical_admission=False,
            financial_recovery_proven=False,external_manifest_attested=False,request_construction_correction_only=False,
            additional_source_edits=['Main._history_fixed_mixed_tick_counts_and_two_call_bounds',
                'Main._probe_SPY_then_exact_parent_tick_window','Main._bound_frozen_config_identity',
                'remove_unused_five_session_calendar_helper','closed_tick_config_and_safe_result_schemas'])
    except (prior.NativeEndpointProbeRefusal,ValueError,TypeError,SyntaxError,UnicodeError,StopIteration):_fail()
    return source,(json.dumps(report,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)+'\n').encode('ascii')
