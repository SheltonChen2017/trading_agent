"""Pure five-session post-gap probe renderer; no native/private effects here.

Preserves the exact control003 and prior diagnostics. Parent failure remains
2021-02-10; the new NONECONOMIC child runs2021-02-12 at16:01. Only same-SID RAW
regular-hours non-fill-forward observations are counted by public date offset.
No past mark is filled, no financial arm is changed, no absence/terminal proof.
"""
from __future__ import annotations

import ast
import hashlib
import json

from . import comparison_20261028_mark_probe_control as control

CONTROL_SHA256='c7337090cc336472576abe4126c20317de47f31e5b9f59fb93eef36520b7662a'


class PostGapProbeRefusal(ValueError):
    """Body-free invalid public source or closed diagnostic scope."""


def _fail():
    raise PostGapProbeRefusal('fixed post-gap native mark probe refused') from None


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


HISTORY = r'''    def _session_windows(self,symbol,label):
        if type(label) is not str or label not in ('control','target'):
            raise ProbeRefusal('native_regular_calendar_unproved')
        from QuantConnect.Securities import Security, SecurityExchangeHours
        def inspect():
            security=self.securities[symbol]
            if (not isinstance(security,Security) or security.symbol.id!=symbol.id
                    or symbol.id.security_type!=SecurityType.EQUITY or symbol.id.market!=Market.USA):
                raise ProbeRefusal('native_regular_calendar_unproved')
            hours=security.exchange.hours
            if not isinstance(hours,SecurityExchangeHours) or hours.time_zone.Id!='America/New_York':
                raise ProbeRefusal('native_regular_calendar_unproved')
            now=self.time.replace(tzinfo=NY) if self.time.tzinfo is None else self.time.astimezone(NY)
            windows={}
            failed=date.fromisoformat(PROBE_CONFIG['failure_session'])
            for offset in (-2,-1,0,1,2):
                day=failed+timedelta(days=offset);midnight=datetime.combine(day,time())
                opened=self._effect('native_calendar_'+label+'_open',lambda:hours.get_next_market_open(midnight,False))
                closed=self._effect('native_calendar_'+label+'_close',lambda:hours.get_next_market_close(midnight,False))
                if not isinstance(opened,datetime) or not isinstance(closed,datetime):
                    raise ProbeRefusal('native_regular_calendar_unproved')
                opened=opened.replace(tzinfo=NY) if opened.tzinfo is None else opened.astimezone(NY)
                closed=closed.replace(tzinfo=NY) if closed.tzinfo is None else closed.astimezone(NY)
                # These five fixed February weekdays are regular USA sessions.
                if (opened.date()!=day or closed.date()!=day or opened.time().replace(tzinfo=None)!=time(9,30)
                        or closed.time().replace(tzinfo=None)!=time(16) or not opened<closed<=now):
                    raise ProbeRefusal('native_regular_calendar_unproved')
                windows[offset]=(opened,closed)
            return windows
        windows=self._effect('native_calendar_'+label,inspect)
        self._report['native_regular_calendars'][label]={'verified':True,'session_count':5,
            'exact_equity_usa':True,'native_hours_new_york':True,'final_close_before_now':True}
        return windows

    def _history(self,symbol,start,end,resolution,maximum,windows,label):
        if label not in ('control_minute','control_daily','minute','daily'):
            raise ProbeRefusal('history_label_unproved')
        expected=2400 if resolution==Resolution.MINUTE else 5 if resolution==Resolution.DAILY else None
        if (expected is None or type(maximum) is not int or maximum!=expected
                or label.endswith('minute')!=(resolution==Resolution.MINUTE)
                or type(start) is not datetime or start!=datetime(2021,2,8)
                or type(end) is not datetime or end!=datetime(2021,2,12,16,1)
                or type(windows) is not dict or set(windows)!=set((-2,-1,0,1,2))):
            raise ProbeRefusal('post_gap_history_scope_unproved')
        def request():
            if self._report['history_calls']>=4:raise ProbeRefusal('history_call_bound')
            method=self.history[TradeBar];self._report['history_calls']+=1
            return method(symbol,start,end,resolution,fill_forward=False,extended_market_hours=False,
                data_normalization_mode=DataNormalizationMode.RAW)
        stream=self._effect('history_'+label+'_request',request)
        iterator=self._effect('history_'+label+'_iterate',lambda:iter(stream))
        by_offset={str(offset):{'rows':0,'positive_volume_rows':0,'nonnegative_volume_rows':0,
            'native_regular_close_rows':0,'all_volume_nonnegative':None} for offset in (-2,-1,0,1,2)}
        count=0;bounded=False;sentinel=object();failed=date.fromisoformat(PROBE_CONFIG['failure_session'])
        for _ in range(maximum):
            bar=self._effect('history_'+label+'_enumerate',lambda:next(iterator,sentinel))
            if bar is sentinel:break
            def inspect():
                if not isinstance(bar,TradeBar) or bar.symbol.id!=symbol.id or bar.is_fill_forward is not False:
                    raise ProbeRefusal('history_row_type_identity_or_fillforward')
                ended=bar.end_time
                if not isinstance(ended,datetime):raise ProbeRefusal('history_row_clock')
                ended=ended.replace(tzinfo=NY) if ended.tzinfo is None else ended.astimezone(NY)
                offset=(ended.date()-failed).days
                if offset not in windows or not start.replace(tzinfo=NY)<ended<=end.replace(tzinfo=NY):
                    raise ProbeRefusal('history_row_outside_request')
                opened,closed=windows[offset]
                if not opened<ended<=closed or resolution==Resolution.DAILY and ended!=closed:
                    raise ProbeRefusal('native_regular_history_endpoint_unproved')
                _probe_number(bar.close)  # Validate privately; never export the value.
                volume=bar.volume
                if hasattr(volume,'ToString'):
                    from System.Globalization import CultureInfo
                    text=volume.ToString(CultureInfo.InvariantCulture)
                elif type(volume) in (str,int,float,Decimal):text=str(volume)
                else:raise ProbeRefusal('native_volume_representation')
                if len(text)>128:raise ProbeRefusal('native_volume_representation')
                amount=Decimal(text)
                if not amount.is_finite() or abs(amount)>Decimal('1e18'):
                    raise ProbeRefusal('native_volume_representation')
                return str(offset),ended==closed,amount>0,amount>=0
            offset,at_close,positive,nonnegative=self._effect('history_'+label+'_inspect',inspect)
            cell=by_offset[offset];cell['rows']+=1;cell['native_regular_close_rows']+=at_close
            cell['positive_volume_rows']+=positive;cell['nonnegative_volume_rows']+=nonnegative
            cell['all_volume_nonnegative']=cell['rows']==cell['nonnegative_volume_rows'];count+=1
        else:bounded=True
        self._report[label]={'rows':count,'by_failure_date_offset':by_offset,
            'all_exact_sid':True if count else None,'all_non_fill_forward':True if count else None,
            'all_positive_finite_closes':True if count else None,'all_native_regular_endpoints':True if count else None,
            'all_end_not_after_request':True if count else None,'row_bound_reached_result_may_be_incomplete':bounded}
'''


QUERY_BLOCK = '''            start=datetime(2021,2,8)
            end=self.time.replace(tzinfo=None)
            control_windows=self._session_windows(self._clock,'control')
            self._history(self._clock,start,end,Resolution.MINUTE,2400,control_windows,'control_minute')
            self._history(self._clock,start,end,Resolution.DAILY,5,control_windows,'control_daily')
            minute_cells=self._report['control_minute']['by_failure_date_offset']
            daily_cells=self._report['control_daily']['by_failure_date_offset']
            controls=all(minute_cells[str(offset)]['positive_volume_rows']>0
                and minute_cells[str(offset)]['all_volume_nonnegative'] is True
                and daily_cells[str(offset)]['rows']==1 and daily_cells[str(offset)]['positive_volume_rows']==1
                and daily_cells[str(offset)]['native_regular_close_rows']==1
                and daily_cells[str(offset)]['all_volume_nonnegative'] is True for offset in (-2,-1,0,1,2))
            self._report['control_request_path_status']='positive_five_session_controls_observed' if controls else 'request_path_unproved'
            self._register_parent(symbol)
            target_windows=self._session_windows(symbol,'target')
            self._history(symbol,start,end,Resolution.MINUTE,2400,target_windows,'minute')
            self._history(symbol,start,end,Resolution.DAILY,5,target_windows,'daily')
            self._report['target_post_failure_rows_observed']={label:any(
                self._report[label]['by_failure_date_offset'][str(offset)]['rows']>0 for offset in (1,2))
                for label in ('minute','daily')}
            self._report.update(status='completed_post_gap_observations' if controls else 'request_path_unproved',phase='complete')'''


def build_mark_probe_post_gap(*,control_source,base_probe_source,helper_source,producer_source,operation_id,git_head):
    """Render one plaintext main.py, no reads, claims, upload, compile or job."""
    if type(control_source) is not bytes or _sha(control_source)!=CONTROL_SHA256:_fail()
    try:
        raw,report_raw=control.build_mark_probe_control(base_probe_source=base_probe_source,helper_source=helper_source,
            producer_source=producer_source,operation_id=operation_id,git_head=git_head,failure_session='2021-02-10')
        source=raw.decode('utf-8');main=next(node for node in ast.parse(source).body if isinstance(node,ast.ClassDef) and node.name=='Main')
        history=next(node for node in main.body if isinstance(node,ast.FunctionDef) and node.name=='_history')
        source=control._replace_node(source,history,HISTORY[4:])
        source=control._replace_once(source,'from datetime import date, time, timezone','from datetime import date, time, timedelta, timezone')
        source=control._replace_once(source,"'native_exact_subscription_type_or_identity','native_exact_subscription_config_unproved'))",
            "'native_exact_subscription_type_or_identity','native_exact_subscription_config_unproved',\n    'native_regular_calendar_unproved','native_regular_history_endpoint_unproved','post_gap_history_scope_unproved','post_gap_runtime_clock_unproved'))")
        source=control._replace_once(source,"'schema':'tpr-cmp28-native-mark-probe-control-result-v1'","'schema':'tpr-cmp28-native-mark-probe-post-gap-result-v1'")
        source=control._replace_once(source,"'target_data_gap_proven':False,'native_exact_subscription':",
            "'target_data_gap_proven':False,'universal_absence_proven':False,'terminal_proven':False,\n            'diagnostic_only_no_financial_recovery':True,'native_regular_calendars':{'control':None,'target':None},\n            'target_post_failure_rows_observed':None,'native_exact_subscription':")
        # Guard the genuine child clock before every private/native effect.
        tree=ast.parse(source);main=next(node for node in tree.body if isinstance(node,ast.ClassDef) and node.name=='Main')
        bound=next(node for node in main.body if isinstance(node,ast.FunctionDef) and node.name=='_bound')
        lines=source.splitlines(keepends=True);bound_raw=''.join(lines[bound.lineno-1:bound.end_lineno])
        addition="""
        local=self.time.replace(tzinfo=NY) if self.time.tzinfo is None else self.time.astimezone(NY)
        utc=self.utc_time.replace(tzinfo=timezone.utc) if self.utc_time.tzinfo is None else self.utc_time.astimezone(timezone.utc)
        if (local.date().isoformat()!=PROBE_CONFIG['diagnostic_session'] or local.time().replace(tzinfo=None)!=time(16,1)
                or local.astimezone(timezone.utc)!=utc):
            raise ProbeRefusal('post_gap_runtime_clock_unproved')"""
        source=control._replace_node(source,bound,bound_raw[4:].rstrip()+addition)
        source=control._replace_once(source,'or parent_algorithm.date()!=self.time.date() or parent_algorithm.time().replace(tzinfo=None)!=time(16,1)',
            'or parent_algorithm.time().replace(tzinfo=None)!=time(16,1)')
        old="""            start=datetime.combine(parent_algorithm.date(),time())
            end=min(parent_algorithm.replace(tzinfo=None),self.time)
            parent_close=datetime.fromisoformat(body['expected_close_local'])
"""+control.TARGET_BLOCK
        source=control._replace_once(source,old,QUERY_BLOCK)
        config_node=next(node for node in ast.parse(source).body if isinstance(node,ast.Assign) and len(node.targets)==1
            and isinstance(node.targets[0],ast.Name) and node.targets[0].id=='PROBE_CONFIG_JSON')
        config=json.loads(ast.literal_eval(config_node.value))
        config.update(schema='tpr-cmp28-native-mark-probe-post-gap-config-v1',control_source_sha256=CONTROL_SHA256,
            configured_session='2021-02-12',diagnostic_session='2021-02-12',history_start_session='2021-02-08',
            history_end_local='2021-02-12T16:01:00',allowed_failure_date_offsets=[-2,-1,0,1,2],
            max_minute_rows=2400,max_daily_rows=5,max_native_calendar_sessions_per_symbol=5,max_native_market_hours_calls=20)
        config_raw=json.dumps(config,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')
        digest=_sha(config_raw)
        source=control._assignment(source,'PROBE_CONFIG_JSON',repr(config_raw.decode('ascii')))
        source=control._assignment(source,'PROBE_CONFIG_SHA256',repr(digest)).encode('utf-8')
        if not 0<len(source)<=60000:_fail()
        compile(ast.parse(source),'main.py','exec')
        report=json.loads(report_raw)
        report.update(schema='tpr-cmp28-mark-probe-post-gap-build-v1',control_source_sha256=CONTROL_SHA256,
            config_sha256=digest,main_sha256=_sha(source),main_bytes=len(source),diagnostic_session='2021-02-12',
            history_start_session='2021-02-08',history_end_local='2021-02-12T16:01:00',
            allowed_failure_date_offsets=[-2,-1,0,1,2],max_minute_rows_per_symbol=2400,max_daily_rows_per_symbol=5,
            max_minute_rows=2400,max_daily_rows=5,max_total_history_rows=4810,max_native_calendar_sessions_per_symbol=5,
            max_native_market_hours_calls=20,
            universal_absence_proven=False,terminal_proven=False,financial_recovery_proven=False,
            additional_source_edits=['Main._history_offset_counts','Main._session_windows_typed_native_regular_calendar',
                'Main._bound_closed_child_clock','parent_failure_and_child_diagnostic_sessions_separated',
                'four_queries_five_session_window','closed_post_gap_config_and_safe_result_fields'])
    except (control.ControlledProbeRefusal,ValueError,TypeError,SyntaxError,UnicodeError,StopIteration):_fail()
    return source,(json.dumps(report,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)+'\n').encode('ascii')
