"""Pure renderer for one NONECONOMIC in-cloud OFF4 mark diagnostic.

Only two exact PUBLIC sources and fixed parent metadata are accepted. No
private file, ObjectStore, credential, provider, compile or job is touched here.
The generated single main.py retains the reviewed mark_read definitions intact.
Initialize has zero private effects: real AlgorithmId is assigned after setup.
The locked16:01 callback independently observes parent existence/hash/schema
before bounded exact-SID history. No order, cache update or price substitution.

Primary lifecycle: Engine/Engine.cs295-311; BacktestingSetupHandler.cs169-200.
Primary SID recipe: Common/Orders/OrderEvent.cs316-317 (Parse then Symbol).
HistoryRequestFactory.cs52-100 and history provider193-200 define explicit
RAW/noFF/date-range semantics. Deployed ABI/backend custody remain unproved.
"""
from __future__ import annotations

import ast
from datetime import date
import hashlib
import json

from . import comparison_20261028_mark_read as reader

HELPER_SHA256 = '6539ae749aefb4884ed52258fc2f0f77c9481a5e8ee37ea80ec7065218f0da95'
PRODUCER_SHA256 = '27c6516b9dfd2d1e71f0ef8fbdb7c371266e36e11bd9e3089e2ce6b76d25aee0'
PARENT_JOB = '12dd4732ba5d9d8f57950beb2a371c79'
PARENT_CONFIG = 'b3d71478e7318b4c0771038617269bf263fa5a1e8edd764ef85fa9015baf44e7'
PARENT_TEMPLATE = 'fe822e0c106cb333182b6a0e7c2e71b37452d15fc4f1f7a020af15e29e93eb2f'
PARENT_POLICY = '2cfeca1b9058f3587a6d5c98df0e6b1ed10b25cdc4398b24a3525130da6425b2'
PARENT_CALENDAR = '590b0e7c143093ea114783b77d08bf6f72fb85b929d2ea9fb640f9ac6eb0df19'
PARENT_WITNESS = 'eef08aca32b99056dee0ce00389c53a8ee6a1628c29188afd8bebd362fe183dd'
PARENT_BYTES = 1343
PARENT_OPERATION = 'TPR-CMP28-OFF-ATTEMPT004-20261028'


class MarkProbeBuildRefusal(ValueError):
    """Body-free invalid public source/metadata framing."""


def _refuse():
    raise MarkProbeBuildRefusal('fixed native mark probe build refused') from None


NATIVE_SOURCE = r'''
from AlgorithmImports import *
from datetime import date, time, timezone
from decimal import Decimal, InvalidOperation
from fractions import Fraction


PROBE_CODES = frozenset(('parent_byte_bound','parent_byte_type_or_bound','native_price_representation',
    'config_digest','initialize_custody_unproved','runtime_custody_unproved','runtime_custody_changed',
    'history_call_bound','history_row_type_identity_or_fillforward','history_row_clock','history_row_outside_request',
    'parent_contains_unknown','parent_exact_hash_or_size_mismatch','parent_session_or_valuation_clock_mismatch',
    'native_identity_framing_unproved','native_identity_roundtrip_unproved'))


class ProbeRefusal(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__('bounded mark probe refused')


class ProbeStopped(BaseException):
    pass


def _probe_bytes(value):
    if type(value) is bytes:
        raw = value
    elif type(value) is bytearray:
        if not 0 < len(value) <= 4096: raise ProbeRefusal('parent_byte_bound')
        raw = bytes(value)
    else:
        from System import Array, Byte
        if type(value) is not Array[Byte] or not 0 < value.Length <= 4096:
            raise ProbeRefusal('parent_byte_type_or_bound')
        raw = bytes(value)
    if not 0 < len(raw) <= 4096: raise ProbeRefusal('parent_byte_bound')
    return raw


def _probe_number(value):
    if hasattr(value,'ToString'):
        from System.Globalization import CultureInfo
        text = value.ToString(CultureInfo.InvariantCulture)
    elif type(value) in (str,int,float,Decimal):
        text = str(value)
    else: raise ProbeRefusal('native_price_representation')
    if len(text)>128: raise ProbeRefusal('native_price_representation')
    value = Decimal(text)
    if not value.is_finite() or not 0 < value <= Decimal('1e18'):
        raise ProbeRefusal('native_price_representation')
    return Fraction(value)


class Main(QCAlgorithm):
    def initialize(self):
        self._phase = 'initialize'
        self._child_job = None
        self._called = False
        self._disabled = False
        self._clock_bars = 0
        self._report = {'schema':'tpr-cmp28-native-mark-probe-result-v1',
            'operation_id':PROBE_CONFIG['operation_id'], 'root_head':PROBE_CONFIG['git_head'],
            'config_sha256':PROBE_CONFIG_SHA256, 'helper_sha256':PROBE_CONFIG['helper_sha256'],
            'parent_job_id':PROBE_CONFIG['binding']['job_id'], 'actual_child_job_id':None,
            'parent_key_sha256':_sha(PROBE_CONFIG['binding']['key'].encode()),
            'parent_witness_sha256':PROBE_CONFIG['binding']['expected_sha256'],
            'parent_witness_bytes':PROBE_CONFIG['binding']['expected_bytes'],
            'status':'scheduled_callback_not_fired', 'phase':'initialize', 'error_class':None,
            'parent_contains':None, 'parent_hash_verified':False, 'parent_schema_verified':False,
            'parent_session_matches_config':False, 'security_id_sha256':None,
            'parent_predicates':None, 'parent_observed_minus_expected_microseconds':None,
            'native_identity_roundtrip':None, 'native_daily_precise_setting':None,
            'contains_calls':0, 'read_calls':0, 'history_calls':0,
            'minute':None, 'daily':None, 'minute_daily_close_price_parity':None,
            'noneconomic_diagnostic':True, 'one_of_five_economic_arms':False,
            'backend_durability_proven':False, 'source_inputs_admitted':False,
            'strategy_accepted':False, 'canonical_admission':False}
        try:
            if _sha(PROBE_CONFIG_JSON.encode('ascii')) != PROBE_CONFIG_SHA256:
                raise ProbeRefusal('config_digest')
            _binding_v2(PROBE_CONFIG['binding'])
            validate_pointer_v2(PROBE_CONFIG['pointer'],binding=PROBE_CONFIG['binding'])
            self.set_time_zone('America/New_York')
            day = date.fromisoformat(PROBE_CONFIG['configured_session'])
            self.set_start_date(day.year,day.month,day.day)
            self.set_end_date(day.year,day.month,day.day)
            # Engine has not assigned its actual runtime job at this stage.
            # This is setup only; no private reader or History exists here.
            if self.live_mode is not False or type(self.project_id) is not int or self.project_id != PROJECT or self.get_locked() is not False:
                raise ProbeRefusal('initialize_custody_unproved')
            self._clock = self.add_equity('SPY',Resolution.MINUTE,
                extended_market_hours=True,data_normalization_mode=DataNormalizationMode.RAW).symbol
            self.set_benchmark(self._clock)
            self.schedule.on(self.date_rules.every_day(self._clock),self.time_rules.at(16,1),self._probe)
        except KeyboardInterrupt:
            raise KeyboardInterrupt('CMP28 mark probe cancelled') from None
        except Exception as error:
            self._disabled = True
            self._record_error(error)
        except BaseException:
            raise ProbeStopped('CMP28 mark probe stopped') from None

    def _record_error(self,error):
        allowed = (ProbeRefusal,MarkReadRefusal,ValueError,TypeError,AttributeError,KeyError,ImportError,OverflowError)
        self._report.update(status=error.code if type(error) is ProbeRefusal and type(error.code) is str and error.code in PROBE_CODES else 'ordinary_native_or_schema_failure',
            phase=self._phase,error_class=next((kind.__name__ for kind in allowed if type(error) is kind),'Exception'))

    def _bound(self):
        job = self.algorithm_id
        if (self.live_mode is not False or type(self.project_id) is not int or self.project_id != PROJECT
                or self.get_locked() is not True or type(job) is not str
                or re.fullmatch('[a-f0-9]{32}',job) is None or job == PROBE_CONFIG['binding']['job_id']):
            raise ProbeRefusal('runtime_custody_unproved')
        if self._child_job is None:
            self._child_job = job
            self._report['actual_child_job_id'] = job
        elif self._child_job != job:
            raise ProbeRefusal('runtime_custody_changed')

    def _effect(self,phase,call):
        self._phase = phase
        self._bound()
        try:
            value = call()
        except BaseException as first:
            try: self._bound()
            except BaseException as second:
                if isinstance(second,KeyboardInterrupt): raise second
                if isinstance(first,KeyboardInterrupt) or not isinstance(first,Exception): raise first
                if not isinstance(second,Exception): raise second
            raise
        self._bound()
        return value

    def on_data(self,data):
        # Exactly one one-day minute clock, at most1440 delivered bars.
        if self._disabled: return
        self._clock_bars += len(data.bars)
        if self._clock_bars >= 1440:
            self._disabled = True
            self._report.update(status='clock_bar_bound',phase='clock',error_class=None)
            self.quit('CMP28 bounded mark probe clock stop')

    def _history(self,symbol,start,end,resolution,maximum,parent_close,parent_day):
        label = 'minute' if resolution == Resolution.MINUTE else 'daily'
        def request():
            method = self.history[TradeBar]
            self._report['history_calls'] += 1
            if self._report['history_calls']>2: raise ProbeRefusal('history_call_bound')
            return method(symbol,start,end,resolution,fill_forward=False,extended_market_hours=False,
                data_normalization_mode=DataNormalizationMode.RAW)
        stream = self._effect('history_'+label+'_request',request)
        iterator = self._effect('history_'+label+'_iterate',lambda:iter(stream))
        count=current=at_close=0
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
                return ended.date()==parent_day, ended==parent_close, _probe_number(bar.close)
            same,equals,price=self._effect('history_'+label+'_inspect',inspect)
            count+=1;current+=same;at_close+=equals
            if equals:prices.append(price)
        else: bounded=True
        self._report[label]={'rows':count,'current_session_rows':current,'end_equals_parent_close_rows':at_close,
            'all_exact_sid':True if count else None,'all_non_fill_forward':True if count else None,'all_end_not_after_request':True if count else None,
            'row_bound_reached_result_may_be_incomplete':bounded}
        return prices

    def _probe(self):
        if self._called or self._disabled: return
        self._called=True
        try:
            self._bound()
            binding=PROBE_CONFIG['binding'];key=binding['key']
            def contains():
                self._report['contains_calls']+=1
                return self.object_store.contains_key(key)
            present=self._effect('contains_parent',contains)
            if type(present) is not bool: raise ProbeRefusal('parent_contains_unknown')
            self._report['parent_contains']=present
            if not present:
                self._report.update(status='parent_missing_in_current_job',phase='contains_parent')
                return
            def read():
                self._report['read_calls']+=1
                return self.object_store.read_bytes(key)
            raw=_probe_bytes(self._effect('read_parent',read))
            if len(raw)!=binding['expected_bytes'] or _sha(raw)!=binding['expected_sha256']:
                raise ProbeRefusal('parent_exact_hash_or_size_mismatch')
            self._report['parent_hash_verified']=True
            safe=self._effect('validate_parent',lambda:project_witness_v2(raw,binding=binding,pointer=PROBE_CONFIG['pointer']))
            body=self._effect('parse_parent',lambda:_parse(raw))
            del raw
            self._body=body  # PRIVATE within this actual runtime only.
            self._report.update(parent_schema_verified=True,security_id_sha256=safe['security_id_sha256'],
                parent_predicates=safe['predicates'],parent_observed_minus_expected_microseconds=safe['observed_minus_expected_microseconds'])
            if PROBE_CONFIG['failure_session'] is None:
                self._report.update(status='failure_session_unavailable_no_history',phase='validate_parent')
                return
            parent_algorithm=datetime.fromisoformat(body['algorithm_local'])
            now=self.utc_time.replace(tzinfo=timezone.utc) if self.utc_time.tzinfo is None else self.utc_time.astimezone(timezone.utc)
            if (parent_algorithm.date().isoformat()!=PROBE_CONFIG['failure_session']
                    or parent_algorithm.date()!=self.time.date() or parent_algorithm.time().replace(tzinfo=None)!=time(16,1)
                    or parent_algorithm>now):
                raise ProbeRefusal('parent_session_or_valuation_clock_mismatch')
            self._report['parent_session_matches_config']=True
            sid_text=body['security_id']
            # Only an already-native-produced, exact-hash-verified EQUITY SID
            # reaches Parse. Reject malformed framing without Parse's internal log.
            pieces=sid_text.split(' ')
            if len(pieces)!=2 or re.fullmatch(r'[^\s|]{1,64}',pieces[0]) is None or re.fullmatch('[A-Z0-9]{1,13}',pieces[1]) is None or int(pieces[1],36)>=2**64:
                raise ProbeRefusal('native_identity_framing_unproved')
            def identity():
                parsed=SecurityIdentifier.parse(sid_text)
                exact=Symbol(parsed,parsed.symbol)
                if (not isinstance(parsed,SecurityIdentifier) or not isinstance(exact,Symbol)
                        or parsed.security_type!=SecurityType.EQUITY or parsed.market!=Market.USA
                        or str(parsed)!=sid_text or str(exact.id)!=sid_text):
                    raise ProbeRefusal('native_identity_roundtrip_unproved')
                return exact
            symbol=self._effect('identity_roundtrip',identity)
            self._report['native_identity_roundtrip']=True
            setting=getattr(self.settings,'daily_precise_end_time',None)
            self._report['native_daily_precise_setting']=setting if type(setting) is bool else None
            start=datetime.combine(parent_algorithm.date(),time())
            end=min(parent_algorithm.replace(tzinfo=None),self.time)
            parent_close=datetime.fromisoformat(body['expected_close_local'])
            minute=self._history(symbol,start,end,Resolution.MINUTE,1000,parent_close,parent_algorithm.date())
            daily=self._history(symbol,start,end,Resolution.DAILY,2,parent_close,parent_algorithm.date())
            if len(minute)==len(daily)==1:
                self._report['minute_daily_close_price_parity']=minute[0]==daily[0]
            self._report.update(status='completed_bounded_diagnostic',phase='complete')
        except KeyboardInterrupt:
            raise KeyboardInterrupt('CMP28 mark probe cancelled') from None
        except Exception as error:
            self._record_error(error)
        except BaseException:
            raise ProbeStopped('CMP28 mark probe stopped') from None

    def on_end_of_algorithm(self):
        try:
            job=self.algorithm_id
            valid=(type(self.project_id) is int and self.project_id==PROJECT and self.get_locked() is True
                and type(job) is str and re.fullmatch('[a-f0-9]{32}',job) is not None and job!=PROBE_CONFIG['binding']['job_id']
                and (self._child_job is None or job==self._child_job))
            self._report['end_runtime_custody']=valid
            if valid:self._report['actual_child_job_id']=job
        except KeyboardInterrupt:
            raise KeyboardInterrupt('CMP28 mark probe cancelled') from None
        except Exception as error:
            self._phase='end_metadata';self._record_error(error)
        except BaseException:
            raise ProbeStopped('CMP28 mark probe stopped') from None
        self._report['clock_bars']=self._clock_bars
        self.log('CMP28_MARK_PROBE_RESULT '+json.dumps(self._report,sort_keys=True,separators=(',',':'),allow_nan=False))
'''


def build_mark_probe(*, helper_source, producer_source, operation_id, git_head, failure_session):
    """Return(main.py bytes, safe report bytes); no private/native effect."""
    if (type(helper_source) is not bytes or hashlib.sha256(helper_source).hexdigest()!=HELPER_SHA256
            or type(producer_source) is not bytes or hashlib.sha256(producer_source).hexdigest()!=PRODUCER_SHA256):
        _refuse()
    try:
        reader._identity(operation_id,'TPR-CMP28-MARK-PROBE-');reader._hash(git_head,40)
        if failure_session is not None:
            if type(failure_session) is not str or date.fromisoformat(failure_session).isoformat()!=failure_session or not '2021-01-04'<=failure_session<='2026-10-09':
                _refuse()
        binding=reader.prepare_binding_v2(operation_id=operation_id,git_head=git_head,
            source_hashes={reader.MODULE:HELPER_SHA256,reader.PRODUCER:PRODUCER_SHA256},
            off_operation_id=PARENT_OPERATION,attempt=4,job_id=PARENT_JOB,config_sha256=PARENT_CONFIG,
            source_template_closure_sha256=PARENT_TEMPLATE,policy_sha256=PARENT_POLICY,calendar_sha256=PARENT_CALENDAR,
            expected_sha256=PARENT_WITNESS,expected_bytes=PARENT_BYTES)
        pointer={'schema':'tpr-cmp28-mark-refusal-pointer-v2','status':'verified','key':binding['key'],'bytes':PARENT_BYTES,
            'expected_sha256':PARENT_WITNESS,'verified_sha256':PARENT_WITNESS,'readback_verified':True,'data_type':'trade_bar',
            'predicates':{'observed_equals_expected':False,'expected_date_equals_algorithm':True,
                'observed_date_equals_session':False,'observed_relation':'before'},
            'reason_code':'minute_or_native_close_wrong_day_or_future','valuation_verification_mode':reader.V2_MODE}
        reader.validate_pointer_v2(pointer,binding=binding)
        config={'schema':'tpr-cmp28-native-mark-probe-config-v1','operation_id':operation_id,'git_head':git_head,
            'helper_sha256':HELPER_SHA256,'producer_sha256':PRODUCER_SHA256,'binding':binding,'pointer':pointer,
            'failure_session':failure_session,'configured_session':failure_session or '2021-01-04',
            'initialize_private_effects':False,'max_parent_contains':1,'max_parent_reads':1,'max_parent_bytes':4096,
            'max_history_calls':2,'max_minute_rows':1000,'max_daily_rows':2,'max_clock_bars':1440,
            'orders_authorized':False,'native_effects_authorized':False,'external_operation_manifest_required':True}
        config_raw=reader._canonical(config);config_hash=hashlib.sha256(config_raw).hexdigest()
        source=helper_source+b'\n'+('PROBE_CONFIG_JSON = '+repr(config_raw.decode('ascii'))+'\nPROBE_CONFIG_SHA256 = '+repr(config_hash)+'\nPROBE_CONFIG = json.loads(PROBE_CONFIG_JSON)\n').encode('ascii')+NATIVE_SOURCE.encode('utf-8')
        if not 0<len(source)<=60000:_refuse()
        compile(ast.parse(source),'main.py','exec')
    except (reader.MarkReadRefusal,ValueError,TypeError,UnicodeError,SyntaxError):
        _refuse()
    report={'schema':'tpr-cmp28-mark-probe-build-v1','operation_id':operation_id,'git_head':git_head,
        'config_sha256':config_hash,'main_sha256':hashlib.sha256(source).hexdigest(),'main_bytes':len(source),
        'helper_sha256':HELPER_SHA256,'producer_sha256':PRODUCER_SHA256,'parent_witness_sha256':PARENT_WITNESS,
        'parent_witness_bytes':PARENT_BYTES,'initialize_private_effects':False,'configured_failure_session':failure_session,
        'max_contains':1,'max_reads':1,'max_history_calls':2,'max_minute_rows':1000,'max_daily_rows':2,'max_clock_bars':1440,
        'one_of_five_economic_arms':False,'source_inputs_admitted':False,'native_permission':False,
        'external_operation_manifest_required':True,'new_jobs':0,'new_economic_looks':0,'accepted_performance':None}
    return source,reader._canonical(report)+b'\n'
