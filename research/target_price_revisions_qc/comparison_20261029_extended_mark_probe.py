"""Pure extended-day typed-bar discriminator; no native effects or mark repair.

The seven immutable public predecessors remain unchanged. The generated plain
main uses the reviewed own-job/witness/config/clock guards, then requests four
fixed RAW/no-fill-forward minute histories. Trade and quote observations stay
separate; neither after-hours observations nor absence proves regular no-trade.
"""
from __future__ import annotations

import ast
import hashlib
import json

from . import comparison_20261029_mark_tick_probe as prior

PINS = {'tick_source':'7bc54d85bf7e4d39a185da862934ac29bd683ab2f237fcb360919a31581f7f55',
    'native_post_gap_source':'895ee46d8c802dd707b5f85de21bf43f1e32eaf4f92f99d82f5de4e2b2b03e43',
    'post_gap_source':'bf9c69322c9fb505174908d5acd2fb4ef9ce63f458f5fcb85fea4038f77e84de',
    'control_source':'c7337090cc336472576abe4126c20317de47f31e5b9f59fb93eef36520b7662a',
    'base_probe_source':'708dfff73f636d3a7f8cd4422a726e9b692d1b7ffcaab575e911db0224f7d8fc',
    'helper_source':'6539ae749aefb4884ed52258fc2f0f77c9481a5e8ee37ea80ec7065218f0da95',
    'producer_source':'27c6516b9dfd2d1e71f0ef8fbdb7c371266e36e11bd9e3089e2ce6b76d25aee0'}
DEFINITION = 'CMP28-NATIVE-EXTENDED-MARK-20261029-v1'
CODES = ('extended_history_scope_unproved','extended_history_prerequisites_unproved',
    'extended_native_calendar_unproved','extended_row_type_unproved','extended_identity_or_fillforward_unproved',
    'extended_bar_period_unproved','extended_bar_clock_unproved','extended_bar_outside_request',
    'extended_bar_order_unproved','extended_bar_session_unproved')


class ExtendedMarkProbeBuildRefusal(ValueError):
    """Body-free refusal of an unproved public source or closed diagnostic."""


def _fail():
    raise ExtendedMarkProbeBuildRefusal('fixed extended native mark diagnostic build refused') from None


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


HISTORY = r'''    def _regular_window(self,symbol,label):
        if type(label) is not str or label not in ('control','target'):
            raise ProbeRefusal('extended_native_calendar_unproved')
        from QuantConnect.Securities import Security, SecurityExchangeHours
        def inspect():
            security=self.securities[symbol]
            if (not isinstance(security,Security) or security.symbol.id!=symbol.id
                    or symbol.id.security_type!=SecurityType.EQUITY or symbol.id.market!=Market.USA):
                raise ProbeRefusal('extended_native_calendar_unproved')
            hours=security.exchange.hours
            if not isinstance(hours,SecurityExchangeHours) or hours.time_zone.Id!='America/New_York':
                raise ProbeRefusal('extended_native_calendar_unproved')
            return hours
        hours=self._effect('extended_calendar_'+label+'_inspect',inspect)
        def calendar(which):
            if self._report['native_market_hours_calls']>=4:
                raise ProbeRefusal('extended_native_calendar_unproved')
            self._report['native_market_hours_calls']+=1
            midnight=datetime(2021,2,10)
            return hours.get_next_market_open(midnight,False) if which=='open' else hours.get_next_market_close(midnight,False)
        opened=self._effect('extended_calendar_'+label+'_open',lambda:calendar('open'))
        closed=self._effect('extended_calendar_'+label+'_close',lambda:calendar('close'))
        def validate():
            if not isinstance(opened,datetime) or not isinstance(closed,datetime):
                raise ProbeRefusal('extended_native_calendar_unproved')
            op=opened.replace(tzinfo=NY) if opened.tzinfo is None else opened.astimezone(NY)
            cl=closed.replace(tzinfo=NY) if closed.tzinfo is None else closed.astimezone(NY)
            now=self.time.replace(tzinfo=NY) if self.time.tzinfo is None else self.time.astimezone(NY)
            if (op.date()!=date(2021,2,10) or cl.date()!=date(2021,2,10)
                    or op.time().replace(tzinfo=None)!=time(9,30) or cl.time().replace(tzinfo=None)!=time(16)
                    or not op<cl<=now):
                raise ProbeRefusal('extended_native_calendar_unproved')
            return op,cl
        window=self._effect('extended_calendar_'+label+'_validate',validate)
        self._extended_windows[label]=(symbol,window)
        self._report['native_regular_calendars'][label]={'verified':True,'session_count':1,
            'exact_equity_usa':True,'native_hours_new_york':True,'regular_endpoints_verified':True}

    def _history(self,symbol,start,end,kind,label):
        labels={'control_trade':('control',TradeBar),'control_quote':('control',QuoteBar),
            'target_trade':('target',TradeBar),'target_quote':('target',QuoteBar)}
        if (type(label) is not str or label not in labels or kind is not labels[label][1]
                or type(start) is not datetime or start!=datetime(2021,2,10,4)
                or type(end) is not datetime or end!=datetime(2021,2,10,20)):
            raise ProbeRefusal('extended_history_scope_unproved')
        origin=labels[label][0]
        if (not all(self._report[name] is True for name in ('parent_hash_verified','parent_schema_verified',
                'parent_session_matches_config','native_identity_roundtrip'))
                or origin not in self._extended_windows
                or self._extended_windows[origin][0].id!=symbol.id
                or origin=='target' and self._report['native_exact_subscription'].get('verified') is not True):
            raise ProbeRefusal('extended_history_prerequisites_unproved')
        opened,closed=self._extended_windows[origin][1]
        cell={'status':'unattempted','request_attempted':False,'request_returned':False,
            'rows_encountered':0,'rows_validated':0,'invalid_rows':0,'pre_market_rows':0,
            'regular_session_rows':0,'post_market_rows':0,'end_equals_regular_open_rows':0,
            'start_equals_regular_open_rows':0,'end_equals_regular_close_rows':0,
            'start_equals_regular_close_rows':0,'duplicate_end_rows':0,
            'complete':False,'row_bound_reached_result_may_be_incomplete':False,
            'prices_consumed':False,'volume_consumed':False,'quotes_used_as_trades':False}
        self._report[label]=cell
        def request():
            if self._report['history_calls']>=4:raise ProbeRefusal('history_call_bound')
            self._report['history_calls']+=1;cell['request_attempted']=True;cell['status']='request_in_progress'
            return self.history[kind](symbol,start,end,Resolution.MINUTE,fill_forward=False,
                extended_market_hours=True,data_normalization_mode=DataNormalizationMode.RAW)
        try:
            stream=self._effect('history_'+label+'_request',request)
            cell['request_returned']=True;cell['status']='enumeration_in_progress'
            iterator=self._effect('history_'+label+'_iterate',lambda:iter(stream))
            previous=None;sentinel=object()
            for _ in range(961):
                row=self._effect('history_'+label+'_enumerate',lambda:next(iterator,sentinel))
                if row is sentinel:
                    cell.update(status='complete_bounded_observation',complete=True);break
                # Every encountered source row spends the budget before filtering.
                cell['rows_encountered']+=1;self._report['bar_rows_encountered']+=1
                if self._report['bar_rows_encountered']>3844:raise ProbeRefusal('history_call_bound')
                def inspect():
                    if not isinstance(row,kind):raise ProbeRefusal('extended_row_type_unproved')
                    if row.symbol.id!=symbol.id or row.is_fill_forward is not False:
                        raise ProbeRefusal('extended_identity_or_fillforward_unproved')
                    period=row.period
                    if not isinstance(period,timedelta) or period!=timedelta(minutes=1):
                        raise ProbeRefusal('extended_bar_period_unproved')
                    stamp,ended=row.time,row.end_time
                    if not isinstance(stamp,datetime) or not isinstance(ended,datetime):
                        raise ProbeRefusal('extended_bar_clock_unproved')
                    stamp=stamp.replace(tzinfo=NY) if stamp.tzinfo is None else stamp.astimezone(NY)
                    ended=ended.replace(tzinfo=NY) if ended.tzinfo is None else ended.astimezone(NY)
                    if ended-stamp!=period or stamp.second or stamp.microsecond or ended.second or ended.microsecond:
                        raise ProbeRefusal('extended_bar_period_unproved')
                    if (stamp.date()!=date(2021,2,10) or ended.date()!=date(2021,2,10)
                            or not start.replace(tzinfo=NY)<=stamp<ended<=end.replace(tzinfo=NY)):
                        raise ProbeRefusal('extended_bar_outside_request')
                    if previous is not None and ended<previous:raise ProbeRefusal('extended_bar_order_unproved')
                    segment=('pre_market_rows' if ended<=opened else 'post_market_rows' if stamp>=closed
                        else 'regular_session_rows' if opened<=stamp<ended<=closed else None)
                    if segment is None:raise ProbeRefusal('extended_bar_session_unproved')
                    # No OHLC, midpoint, bid/ask, quote value or volume is read.
                    return ended,segment,ended==opened,stamp==opened,ended==closed,stamp==closed
                try:observed=self._effect('history_'+label+'_inspect',inspect)
                except BaseException:
                    cell['invalid_rows']+=1;raise
                ended,segment,end_open,start_open,end_close,start_close=observed
                cell['duplicate_end_rows']+=previous==ended;previous=ended
                cell['rows_validated']+=1;cell[segment]+=1
                cell['end_equals_regular_open_rows']+=end_open;cell['start_equals_regular_open_rows']+=start_open
                cell['end_equals_regular_close_rows']+=end_close;cell['start_equals_regular_close_rows']+=start_close
            else:cell.update(status='row_bound_incomplete',row_bound_reached_result_may_be_incomplete=True)
        except BaseException:
            if cell['status'] in ('request_in_progress','enumeration_in_progress'):cell['status']='access_or_validation_unproved'
            raise
'''

QUERY = '''            start=datetime(2021,2,10,4)
            end=datetime(2021,2,10,20)
            self._regular_window(self._clock,'control')
            self._history(self._clock,start,end,TradeBar,'control_trade')
            self._history(self._clock,start,end,QuoteBar,'control_quote')
            self._register_parent(symbol)
            self._regular_window(symbol,'target')
            self._history(symbol,start,end,TradeBar,'target_trade')
            self._history(symbol,start,end,QuoteBar,'target_quote')
            complete=all(self._report[label]['complete'] for label in ('control_trade','control_quote','target_trade','target_quote'))
            controls=all(self._report[label]['rows_validated']>0 for label in ('control_trade','control_quote'))
            self._report['control_request_path_status']='positive_typed_bar_controls_observed' if controls else 'request_path_unproved'
            self._report['target_no_rows_observed_in_bound']={kind:(self._report['target_'+kind]['rows_validated']==0
                if complete and self._report['control_'+kind]['rows_validated']>0 else None) for kind in ('trade','quote')}
            self._report.update(status=('completed_bounded_extended_observations' if complete and controls else
                'extended_row_bound_incomplete' if not complete else 'request_path_unproved'),phase='complete')'''


def build_extended_mark_probe(*,tick_source,native_post_gap_source,post_gap_source,control_source,
        base_probe_source,helper_source,producer_source,operation_id,git_head):
    """Return main/report bytes only. Fresh external effect claims remain required."""
    supplied=dict(tick_source=tick_source,native_post_gap_source=native_post_gap_source,post_gap_source=post_gap_source,
        control_source=control_source,base_probe_source=base_probe_source,helper_source=helper_source,producer_source=producer_source)
    if (prior.PINS!={name:value for name,value in PINS.items() if name!='tick_source'}
            or any(type(raw) is not bytes or _sha(raw)!=PINS[name] for name,raw in supplied.items())):_fail()
    try:
        raw,report_raw=prior.build_mark_tick_probe(**{name:value for name,value in supplied.items() if name!='tick_source'},
            operation_id=operation_id,git_head=git_head)
        source=raw.decode('utf-8');control=prior.prior.prior.control
        def method(name):
            main=next(n for n in ast.parse(source).body if isinstance(n,ast.ClassDef) and n.name=='Main')
            nodes=[n for n in main.body if isinstance(n,ast.FunctionDef) and n.name==name]
            if len(nodes)!=1:_fail()
            return nodes[0]
        source=control._replace_node(source,method('_history'),HISTORY[4:])
        source=control._replace_once(source,prior.QUERY,QUERY)
        source=control._replace_once(source,"'schema':'tpr-cmp28-native-mark-tick-probe-result-v1'",
            "'schema':'tpr-cmp28-native-extended-mark-probe-result-v1'")
        source=control._replace_once(source,"'control_ticks':None,'target_ticks':None,\n            'tick_rows_encountered':0,'target_trade_ticks_observed':None,'target_no_trade_ticks_observed_in_bound':None,\n            'mixed_trade_quote_request':True,",
            "'control_trade':None,'control_quote':None,'target_trade':None,'target_quote':None,\n            'bar_rows_encountered':0,'native_market_hours_calls':0,'native_regular_calendars':{'control':None,'target':None},\n            'target_no_rows_observed_in_bound':None,'regular_session_no_trade_proven':False,'provider_hole_excluded':False,\n            'native_routing_fix_proven':False,'quotes_used_as_trades':False,'prices_consumed':False,'volume_consumed':False,")
        source=control._replace_once(source,"        self._phase = 'initialize'","        self._extended_windows={}\n        self._phase = 'initialize'")
        tree=ast.parse(source)
        node=next(n for n in tree.body if isinstance(n,ast.Assign) and len(n.targets)==1
            and isinstance(n.targets[0],ast.Name) and n.targets[0].id=='PROBE_CODES')
        codes=ast.literal_eval(node.value.args[0])
        source=control._assignment(source,'PROBE_CODES','frozenset('+repr(tuple(codes)+CODES)+')')
        node=next(n for n in ast.parse(source).body if isinstance(n,ast.Assign) and len(n.targets)==1
            and isinstance(n.targets[0],ast.Name) and n.targets[0].id=='PROBE_CONFIG_JSON')
        config=json.loads(ast.literal_eval(node.value))
        report=json.loads(report_raw)
        for body in (config,report):
            for name in ('max_tick_rows_per_symbol','max_total_tick_rows','mixed_trade_quote_request','quote_prices_consumed'):
                body.pop(name,None)
        common=dict(diagnostic_definition=DEFINITION,public_source_sha256=dict(PINS),max_history_calls=4,
            max_bar_rows_per_call=961,max_total_history_rows=3844,max_native_market_hours_calls=4,
            history_start_session='2021-02-10',history_start_local='2021-02-10T04:00:00',history_end_local='2021-02-10T20:00:00',
            request_endpoint_construction='fixed_plain_datetime_extended_minute_endpoints_v1',extended_market_hours=True,
            history_resolution='minute',history_types=['TradeBar','QuoteBar'],fill_forward=False,data_normalization_mode='RAW',
            prices_consumed=False,volume_consumed=False,quotes_used_as_trades=False,
            regular_session_no_trade_proven=False,provider_hole_excluded=False,native_routing_fix_proven=False,
            financial_recovery_proven=False,derived_bar_created=False,cache_updated=False,
            native_origin_authenticated=False,point_in_time_verified=False,rights_verified=False,canonical_admission=False,
            sdk_hard_timeout_proven=False,sdk_preallocation_byte_bound_proven=False)
        config.update(common,schema='tpr-cmp28-native-extended-mark-probe-config-v1')
        config_raw=json.dumps(config,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')
        digest=_sha(config_raw)
        source=control._assignment(source,'PROBE_CONFIG_JSON',repr(config_raw.decode('ascii')))
        source=control._assignment(source,'PROBE_CONFIG_SHA256',repr(digest)).encode('utf-8')
        if not 0<len(source)<=60000:_fail()
        compile(ast.parse(source),'main.py','exec')
        report.update(common,schema='tpr-cmp28-extended-mark-probe-build-v1',config_sha256=digest,
            main_sha256=_sha(source),main_bytes=len(source),external_manifest_attested=False,
            request_construction_correction_only=False,additional_source_edits=[
                'Main._regular_window_one_native_session_per_symbol','Main._history_four_typed_extended_minute_calls',
                'Main._probe_independent_trade_quote_controls_and_target','closed_extended_config_and_result_schemas'])
    except (prior.TickProbeBuildRefusal,ValueError,TypeError,SyntaxError,UnicodeError,StopIteration,AttributeError):_fail()
    return source,(json.dumps(report,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)+'\n').encode('ascii')
