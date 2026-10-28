"""Pure controlled-probe renderer; preserves the first native diagnostic.

Exact pinned PUBLIC sources only. Enumerated AST/string edits add two SPY
controls before one genuine exact-SID AddSecurity(Symbol) registration and its
two target queries. All source stays readable plaintext inside one main.py.
No private reader, native effect, permission, compile or job executes here.

Primary exact-symbol registration: QCAlgorithm.cs1846-1908. AddEquity takes a
string; it is NEVER used for the parent Symbol. Native history unsubscribed
fallback exists, but deployed positive controls/registration are observed here
rather than assuming that an empty history proves a data gap.
"""
from __future__ import annotations

import ast
import hashlib
import json

from . import comparison_20261028_mark_probe as base

BASE_SHA256 = '708dfff73f636d3a7f8cd4422a726e9b692d1b7ffcaab575e911db0224f7d8fc'


class ControlledProbeRefusal(ValueError):
    """Fixed body-free invalid public source/edit scope."""


def _fail():
    raise ControlledProbeRefusal('fixed controlled native mark probe refused') from None


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _replace_once(source,old,new):
    if source.count(old)!=1:_fail()
    return source.replace(old,new)


def _replace_node(source,node,replacement):
    lines=source.splitlines(keepends=True)
    if node.end_lineno is None or node.end_col_offset is None:_fail()
    start=sum(map(len,lines[:node.lineno-1]))+node.col_offset
    end=sum(map(len,lines[:node.end_lineno-1]))+node.end_col_offset
    if not source[:end].isascii():_fail()
    return source[:start]+replacement+source[end:]


def _assignment(source,name,replacement):
    nodes=[n for n in ast.parse(source).body if isinstance(n,ast.Assign) and len(n.targets)==1
        and isinstance(n.targets[0],ast.Name) and n.targets[0].id==name]
    if len(nodes)!=1:_fail()
    return _replace_node(source,nodes[0].value,replacement)


HISTORY_AND_REGISTRATION = r'''    def _history(self,symbol,start,end,resolution,maximum,parent_close,parent_day,label=None):
        label = label or ('minute' if resolution == Resolution.MINUTE else 'daily')
        if label not in ('control_minute','control_daily','minute','daily'):
            raise ProbeRefusal('history_label_unproved')
        def request():
            if self._report['history_calls']>=4: raise ProbeRefusal('history_call_bound')
            method = self.history[TradeBar]
            self._report['history_calls'] += 1
            return method(symbol,start,end,resolution,fill_forward=False,extended_market_hours=False,
                data_normalization_mode=DataNormalizationMode.RAW)
        stream = self._effect('history_'+label+'_request',request)
        iterator = self._effect('history_'+label+'_iterate',lambda:iter(stream))
        count=current=at_close=positive=nonnegative=0
        prices=[]
        bounded=False
        sentinel=object()
        for _ in range(maximum):
            bar=self._effect('history_'+label+'_enumerate',lambda:next(iterator,sentinel))
            if bar is sentinel: break
            def inspect():
                if not isinstance(bar,TradeBar) or bar.symbol.id != symbol.id or bar.is_fill_forward is not False:
                    raise ProbeRefusal('history_row_type_identity_or_fillforward')
                ended=bar.end_time
                if not isinstance(ended,datetime): raise ProbeRefusal('history_row_clock')
                ended=ended.replace(tzinfo=NY) if ended.tzinfo is None else ended.astimezone(NY)
                if ended > end.replace(tzinfo=NY) or ended <= start.replace(tzinfo=NY):
                    raise ProbeRefusal('history_row_outside_request')
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
                return ended.date()==parent_day, ended==parent_close, _probe_number(bar.close), amount>0, amount>=0
            same,equals,price,above_zero,at_least_zero=self._effect('history_'+label+'_inspect',inspect)
            count+=1;current+=same;at_close+=equals;positive+=above_zero;nonnegative+=at_least_zero
            if equals:prices.append(price)
        else: bounded=True
        self._report[label]={'rows':count,'current_session_rows':current,'end_equals_parent_close_rows':at_close,
            'positive_volume_rows':positive,'nonnegative_volume_rows':nonnegative,
            'all_volume_nonnegative':nonnegative==count if count else None,
            'all_exact_sid':True if count else None,'all_non_fill_forward':True if count else None,
            'all_end_not_after_request':True if count else None,
            'row_bound_reached_result_may_be_incomplete':bounded}
        return prices

    def _register_parent(self,symbol):
        from QuantConnect.Securities import Security
        from QuantConnect.Data import SubscriptionDataConfig
        from System import Object as NetObject
        provenance=self._report['native_exact_subscription']
        def register():
            method=self.add_security
            provenance['add_security_calls']+=1
            return method(symbol,resolution=Resolution.MINUTE,fill_forward=False,
                extended_market_hours=False,data_normalization_mode=DataNormalizationMode.RAW)
        security=self._effect('register_exact_parent',register)
        def inspect():
            typed=isinstance(security,Security)
            exact=typed and security.symbol.id==symbol.id
            registered=exact and NetObject.ReferenceEquals(self.securities[symbol],security)
            provenance.update(returned_native_security=typed,returned_exact_sid=bool(exact),registered_exact_native_reference=bool(registered))
            if not registered:raise ProbeRefusal('native_exact_subscription_type_or_identity')
            provenance['config_reads']+=1
            config_stream=self.subscription_manager.subscription_data_config_service.get_subscription_data_configs(symbol,True)
            iterator=iter(config_stream);configs=[];sentinel=object()
            for _ in range(65):
                row=next(iterator,sentinel)
                if row is sentinel:break
                configs.append(row)
            if not 0<len(configs)<=64 or any(not isinstance(row,SubscriptionDataConfig) for row in configs):
                raise ProbeRefusal('native_exact_subscription_config_unproved')
            external=[row for row in configs if row.is_internal_feed is False]
            provenance['external_config_count']=len(external)
            exact_ids=all(row.symbol.id==symbol.id for row in external)
            raw=all(row.data_normalization_mode==DataNormalizationMode.RAW for row in external)
            matches=[row for row in external if row.symbol.id==symbol.id
                and row.data_normalization_mode==DataNormalizationMode.RAW and row.resolution==Resolution.MINUTE
                and row.tick_type==TickType.TRADE and row.type.FullName=='QuantConnect.Data.Market.TradeBar'
                and row.fill_data_forward is False and row.extended_market_hours is False and row.is_custom_data is False
                and row.exchange_time_zone.id=='America/New_York']
            provenance.update(all_external_exact_sid=bool(exact_ids) if external else None,
                all_external_raw=bool(raw) if external else None,regular_nonfillforward_raw_minute_trade_configs=len(matches))
            if not external or not exact_ids or not raw or len(matches)!=len(external):
                raise ProbeRefusal('native_exact_subscription_config_unproved')
        self._effect('verify_exact_parent_subscription',inspect)
        # Verification is true only after the post-effect custody guard succeeds.
        provenance['verified']=True
'''


TARGET_BLOCK = '''            # Preserve positive-control observations even if registration fails.
            self._history(self._clock,start,end,Resolution.MINUTE,1000,parent_close,parent_algorithm.date(),label='control_minute')
            self._history(self._clock,start,end,Resolution.DAILY,2,parent_close,parent_algorithm.date(),label='control_daily')
            control_minute=self._report['control_minute'];control_daily=self._report['control_daily']
            controls=all(row['current_session_rows']>0 and row['end_equals_parent_close_rows']>0
                and row['positive_volume_rows']>0 and row['all_volume_nonnegative'] is True
                for row in (control_minute,control_daily))
            self._report['control_request_path_status']='positive_controls_observed' if controls else 'request_path_unproved'
            self._register_parent(symbol)
            minute=self._history(symbol,start,end,Resolution.MINUTE,1000,parent_close,parent_algorithm.date())
            daily=self._history(symbol,start,end,Resolution.DAILY,2,parent_close,parent_algorithm.date())
            if len(minute)==len(daily)==1:
                self._report['minute_daily_close_price_parity']=minute[0]==daily[0]
            self._report.update(status='completed_controlled_diagnostic' if controls else 'request_path_unproved',phase='complete')'''


def build_mark_probe_control(*,base_probe_source,helper_source,producer_source,operation_id,git_head,failure_session='2021-02-10'):
    """Return one plain main.py and build report; grants no native authority."""
    if (type(base_probe_source) is not bytes or _sha(base_probe_source)!=BASE_SHA256
            or failure_session!='2021-02-10'):_fail()
    try:
        raw,base_report=base.build_mark_probe(helper_source=helper_source,producer_source=producer_source,
            operation_id=operation_id,git_head=git_head,failure_session=failure_session)
        tree=ast.parse(base_probe_source)
        native_node=next(n for n in tree.body if isinstance(n,ast.Assign) and len(n.targets)==1
            and isinstance(n.targets[0],ast.Name) and n.targets[0].id=='NATIVE_SOURCE')
        native=ast.literal_eval(native_node.value)
        if type(native) is not str or not raw.endswith(native.encode('utf-8')):_fail()
        main=next(n for n in ast.parse(native).body if isinstance(n,ast.ClassDef) and n.name=='Main')
        history=next(n for n in main.body if isinstance(n,ast.FunctionDef) and n.name=='_history')
        # _replace_node starts at the 'def' after its indentation.
        native=_replace_node(native,history,HISTORY_AND_REGISTRATION[4:])
        native=_replace_once(native,"'native_identity_framing_unproved','native_identity_roundtrip_unproved'))",
            "'native_identity_framing_unproved','native_identity_roundtrip_unproved','history_label_unproved',\n    'native_volume_representation','native_exact_subscription_type_or_identity','native_exact_subscription_config_unproved'))")
        native=_replace_once(native,"'schema':'tpr-cmp28-native-mark-probe-result-v1'","'schema':'tpr-cmp28-native-mark-probe-control-result-v1'")
        native=_replace_once(native,"'minute':None, 'daily':None, 'minute_daily_close_price_parity':None,",
            "'minute':None, 'daily':None, 'minute_daily_close_price_parity':None,\n            'control_minute':None,'control_daily':None,'control_request_path_status':'request_path_unproved',\n            'target_data_gap_proven':False,'native_exact_subscription':{'add_security_calls':0,'config_reads':0,\n                'returned_native_security':None,'returned_exact_sid':None,'registered_exact_native_reference':None,\n                'external_config_count':None,'all_external_exact_sid':None,'all_external_raw':None,\n                'regular_nonfillforward_raw_minute_trade_configs':None,'verified':False},")
        old="""            minute=self._history(symbol,start,end,Resolution.MINUTE,1000,parent_close,parent_algorithm.date())
            daily=self._history(symbol,start,end,Resolution.DAILY,2,parent_close,parent_algorithm.date())
            if len(minute)==len(daily)==1:
                self._report['minute_daily_close_price_parity']=minute[0]==daily[0]
            self._report.update(status='completed_bounded_diagnostic',phase='complete')"""
        native=_replace_once(native,old,TARGET_BLOCK)
        source=raw[:-len(ast.literal_eval(native_node.value).encode('utf-8'))].decode('utf-8')+native
        config_node=next(n for n in ast.parse(source).body if isinstance(n,ast.Assign) and len(n.targets)==1
            and isinstance(n.targets[0],ast.Name) and n.targets[0].id=='PROBE_CONFIG_JSON')
        config=json.loads(ast.literal_eval(config_node.value))
        config.update(schema='tpr-cmp28-native-mark-probe-control-config-v1',base_probe_source_sha256=BASE_SHA256,
            max_history_calls=4,max_native_exact_symbol_registrations=1,max_registration_config_reads=1)
        config_raw=json.dumps(config,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')
        config_hash=_sha(config_raw)
        source=_assignment(source,'PROBE_CONFIG_JSON',repr(config_raw.decode('ascii')))
        source=_assignment(source,'PROBE_CONFIG_SHA256',repr(config_hash)).encode('utf-8')
        if not 0<len(source)<=60000:_fail()
        compile(ast.parse(source),'main.py','exec')
        report=json.loads(base_report)
        report.update(schema='tpr-cmp28-mark-probe-control-build-v1',base_probe_source_sha256=BASE_SHA256,
            config_sha256=config_hash,main_sha256=_sha(source),main_bytes=len(source),max_history_calls=4,
            max_minute_rows_per_symbol=1000,max_daily_rows_per_symbol=2,max_total_history_rows=2004,
            max_native_exact_symbol_registrations=1,max_registration_config_reads=1,max_configs=64,max_config_rows_examined=65,
            source_edits=['Main._history_explicit_labels_four_call_bound_volume_counts','Main._register_parent_native_exact_symbol',
                'closed_safe_reason_codes','controlled_result_schema','control_and_registration_report_fields',
                'SPY_controls_before_parent_registration_and_target_queries','closed_control_config_literals'],
            target_data_gap_proven=False)
    except (base.MarkProbeBuildRefusal,ValueError,TypeError,SyntaxError,UnicodeError,StopIteration):_fail()
    return source,(json.dumps(report,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)+'\n').encode('ascii')
