"""Source-bound candidate bridge for private derived events INSIDE QC.

Preparation is pure supplied-byte processing: no file/ObjectStore/provider API
is reached. Exact plain JSON bounds/hashes precede streaming JSON parse.
Date offsets reference the immutable packet; no second280MB copy or full JSON
tree is retained. All uploaded source and retained data stay readable JSON.
Native historical map resolution occurs only on demand at a decision cutoff.
There is no generic resolver callback, current-ticker/current-delisted screen,
raw target-price packet, map/factor export or self-declared native authority.

The fixed initialized IMapFileProvider, MapFileResolver.ResolveMapFile(ticker,
issued_date), explicit map rows and historical five-argument GenerateEquity
API must agree. Empty/default/future/ambiguous/unsupported maps remain unknown.
Typed stubs prove software only; genuine runtime ABI, custody, rights, historical
PIT and share-basis acceptance remain unproved, even for consistent candidates.

Primary APIs checked2026-10-28:
https://github.com/QuantConnect/Lean/blob/master/Common/Interfaces/IMapFileProvider.cs
https://github.com/QuantConnect/Lean/blob/master/Common/Data/Auxiliary/MapFile.cs
https://github.com/QuantConnect/Lean/blob/master/Common/Data/Auxiliary/MapFileResolver.cs
https://github.com/QuantConnect/Lean/blob/master/Common/SecurityIdentifier.cs
"""
from __future__ import annotations

from bisect import bisect_right
from collections import Counter
from collections.abc import Mapping
from datetime import datetime, time
import hashlib
import json
from types import MappingProxyType
from zoneinfo import ZoneInfo

from . import comparison_20261028_events as events

MAX_PACKET_BYTES = 512 * 1024**2
MAX_EVENT_BYTES = 16384
BLOCK = 65536
PACKET_KEYS = frozenset(("schema","study_id","source_inventory_sha256","events","census"))
CENSUS_KEYS = frozenset(("source_rows","derived_rows","unavailable_rows","refusal_counts","projection_count"))


class NativeSignalError(ValueError):
    """Body-free supplied-packet/native-bridge framing refusal."""


class NativeSignalStopped(BaseException):
    """Body-free nonordinary stop; never demoted to unknown or zero effect."""


def _fail():
    raise NativeSignalError("bounded native signal bridge refused") from None


def _hash(value):
    if type(value) is not str or len(value)!=64 or any(char not in "0123456789abcdef" for char in value): _fail()
    return value


def _bounded(value,maximum,minimum=0):
    if type(value) is not int or not minimum<=value<=maximum: _fail()
    return value


def _stop(error):
    if isinstance(error,KeyboardInterrupt):
        raise KeyboardInterrupt("native signal processing cancelled") from None
    if not isinstance(error,Exception):
        raise NativeSignalStopped("native signal processing stopped") from None
    _fail()


class _JSONStream:
    """Bounded UTF-8 JSON token buffer with absolute packet-byte offsets."""
    def __init__(self,payload):
        self.raw=payload;self.offset=0;self.position=0;self.text="";self.done=False;self.last_span=None
        def pairs(items):
            value={}
            for key,item in items:
                if key in value:_fail()
                value[key]=item
            return value
        def number(text):
            if len(text)>256:_fail()
            return int(text)
        self.decoder=json.JSONDecoder(object_pairs_hook=pairs,parse_int=number,
            parse_float=lambda _: _fail(),parse_constant=lambda _: _fail())

    def more(self):
        if self.done:return False
        block=self.raw[self.offset:self.offset+BLOCK]
        try:text=block.decode("utf-8")
        except UnicodeDecodeError as error:
            if error.reason!="unexpected end of data" or self.offset+len(block)==len(self.raw):raise
            block=block[:error.start];text=block.decode("utf-8")
        if not block:_fail()
        self.offset+=len(block)
        self.text+=text
        self.done=self.offset==len(self.raw)
        return bool(block)

    def consume(self,count):
        self.position+=len(self.text[:count].encode("utf-8"));self.text=self.text[count:]

    def clean(self):
        while True:
            trimmed=self.text.lstrip();self.position+=len(self.text[:len(self.text)-len(trimmed)].encode("utf-8"));self.text=trimmed
            if self.text or self.done:return
            self.more()

    def char(self,expected):
        self.clean()
        if not self.text or self.text[0]!=expected:_fail()
        self.consume(1)

    def value(self,maximum=MAX_EVENT_BYTES):
        self.clean();start=self.position
        while True:
            try:
                value,end=self.decoder.raw_decode(self.text)
                if end>maximum:_fail()
                self.consume(end);self.last_span=(start,self.position)
                return value
            except json.JSONDecodeError:
                if len(self.text)>maximum or self.done:_fail()
                self.more()

    def end(self):
        self.clean()
        if self.text:_fail()
        while not self.done:
            self.more();self.clean()
            if self.text:_fail()


def _native_date(value):
    # Python.NET exposes DateTime properties as datetime in the source-pinned
    # algorithm path. Unsupported CLR wrappers are unknown, never coerced.
    if not isinstance(value,datetime):_fail()
    return value.date()


def _group_key(row):
    identity=row["event_id"]
    return hashlib.sha256(events.canonical([type(identity).__name__,identity])).hexdigest()


class NativeSignals:
    """Private QC runtime object. Publish only public_summary()/binding census.

    scores_for returns private native-SID scores/states for algorithm use. The
    constructor's native provider stays untouched until an eligible event needs
    mapping. The fixed provider is discovered once; a failed API is not retried
    unchanged on every event. No native map row is returned or persisted.
    """
    def __init__(self,raw,sessions,inventory_hash):
        self._sessions=tuple(dict(row) for row in sessions)
        try:axis=events.raw_revision._calendar(list(self._sessions))
        except events.raw_revision.RawRevisionError:_fail()
        normalized=[{"session_date":day.isoformat(),"open_utc":opened.isoformat()} for day,opened in axis]
        if hashlib.sha256(events.canonical(normalized)).hexdigest()!=events.SESSION_AXIS_SHA256:_fail()
        self._days=tuple(day for day,_ in axis);self._opens=tuple(opened for _,opened in axis)
        self._index={};self._binding_cache={};self._map_cache={};self._conflicts=set();self._inconsistent=set()
        self._native=None;self._native_failure=None;self._native_lookups=0
        self._pending_receipts=[];self._binding_chain="0"*64
        self._packet=raw;self._packet_sha256=hashlib.sha256(raw).hexdigest()
        self._inventory_sha256=inventory_hash
        source_meta={};seen_fields=set();source_count=derived_count=unavailable_count=0
        refusals=Counter();first_signature={};version_meta={}
        stream=_JSONStream(raw);stream.char("{")
        previous_day=None;current_day=None;current_start=current_end=current_count=0
        def retain_day():
            if current_day is not None:
                self._index[current_day]=(current_start,current_end,current_count)
        while True:
            stream.clean()
            if stream.text.startswith("}"):
                stream.char("}");break
            field=stream.value(256)
            if type(field) is not str or field not in PACKET_KEYS or field in seen_fields:_fail()
            seen_fields.add(field);stream.char(":")
            if field=="events":
                stream.char("[")
                while True:
                    stream.clean()
                    if stream.text.startswith("]"):
                        stream.char("]");break
                    row=events._event(stream.value())
                    row_start,row_end=stream.last_span
                    day=row["raw_issued_date"]
                    if previous_day is not None and day<previous_day:_fail()
                    previous_day=day
                    if current_day!=day:
                        retain_day();current_day=day;current_start=row_start;current_count=0
                    current_end=row_end;current_count+=1
                    source_count+=1
                    if source_count>events.MAX_EVENTS:_fail()
                    derived_count+=row["state"]=="derived";unavailable_count+=row["state"]=="unavailable"
                    refusals.update(row["refusals"])
                    key=_group_key(row)
                    if row["event_id"] is not None:
                        if key in first_signature and first_signature[key]!=row["source_row_sha256"]:self._conflicts.add(key)
                        else:first_signature[key]=row["source_row_sha256"]
                        if "conflicting_native_event_id" in row["source_refusals"]:self._conflicts.add(key)
                    meta=hashlib.sha256(events.canonical({key:value for key,value in row.items() if key not in
                        ("capture_utc","source_page_sha256","source_ordinal")})).hexdigest()
                    if row["event_key"] in version_meta and version_meta[row["event_key"]]!=meta:self._inconsistent.add(row["event_key"])
                    else:version_meta[row["event_key"]]=meta
                    stream.clean()
                    if stream.text.startswith(","):
                        stream.char(",");stream.clean()
                        if stream.text.startswith("]"):_fail()
                        continue
                    stream.char("]");break
                retain_day();current_day=None
            else:source_meta[field]=stream.value(65536)
            stream.clean()
            if stream.text.startswith(","):
                stream.char(",");stream.clean()
                if stream.text.startswith("}"):_fail()
                continue
            stream.char("}");break
        stream.end()
        if seen_fields!=PACKET_KEYS or source_meta.get("schema")!="tpr-cmp28-derived-nominal-packet-v1" or source_meta.get("study_id")!=events.STUDY or source_meta.get("source_inventory_sha256")!=inventory_hash:_fail()
        census=source_meta.get("census")
        if type(census) is not dict or set(census)!=CENSUS_KEYS:_fail()
        if (type(census["source_rows"]) is not int or census["source_rows"]!=source_count
                or type(census["derived_rows"]) is not int or census["derived_rows"]!=derived_count
                or type(census["unavailable_rows"]) is not int or census["unavailable_rows"]!=unavailable_count
                or census["refusal_counts"]!=dict(sorted(refusals.items()))):_fail()
        if type(census["refusal_counts"]) is not dict or any(type(value) is not int or value<0 for value in census["refusal_counts"].values()):_fail()
        _bounded(census["projection_count"],386)
        if source_count and not census["projection_count"]:_fail()
        self._source_census=json.loads(events.canonical(census))
        self._index=MappingProxyType(self._index)

    def _native_parts(self):
        if self._native is not None:return self._native
        if self._native_failure is not None:return None
        try:
            from QuantConnect import SecurityIdentifier,SecurityType,Market
            from QuantConnect.Interfaces import IMapFileProvider
            from QuantConnect.Util import Composer
            from QuantConnect.Data.Auxiliary import AuxiliaryDataKey,MapFileResolver,MapFile,MapFileRow
            providers=list(Composer.Instance.GetParts[IMapFileProvider]())
            if len(providers)!=1 or not isinstance(providers[0],IMapFileProvider):_fail()
            provider=providers[0]
            resolver=provider.Get(AuxiliaryDataKey.EquityUsa)
            if not isinstance(resolver,MapFileResolver):_fail()
            self._native=(provider,resolver,MapFile,MapFileRow,SecurityIdentifier,SecurityType,Market)
            return self._native
        except BaseException as error:
            if not isinstance(error,Exception):_stop(error)
            self._native_failure="initialized_native_map_provider_unavailable"
            return None

    def _bind(self,ticker,issued):
        key=(ticker,issued.isoformat())
        if key in self._binding_cache:return self._binding_cache[key],True
        status="native_map_unknown";sid=None;row_count=None;row_hash=None
        native=self._native_parts()
        if native is None:status=self._native_failure
        else:
            provider,resolver,MapFile,MapFileRow,SecurityIdentifier,SecurityType,Market=native
            try:
                self._native_lookups+=1
                if self._native_lookups>events.MAX_EVENTS:_fail()
                at=datetime.combine(issued,time())
                mapping=resolver.ResolveMapFile(ticker,at)
                if not isinstance(mapping,MapFile):_fail()
                rows=list(mapping)
                if not 1<=len(rows)<=10000 or any(not isinstance(row,MapFileRow) for row in rows):_fail()
                projection=[]
                for row in rows:
                    day=_native_date(row.Date)
                    if not events.raw_revision._ticker(row.MappedSymbol) or row.DataMappingMode is not None:_fail()
                    projection.append({"date":day.isoformat(),"mapped_symbol":row.MappedSymbol})
                if projection!=sorted(projection,key=lambda row:row["date"]) or len({row["date"] for row in projection})!=len(projection):_fail()
                first,last=_native_date(mapping.FirstDate),_native_date(mapping.DelistingDate)
                if first.isoformat()!=projection[0]["date"] or last.isoformat()!=projection[-1]["date"] or not first<=issued<=last:_fail()
                explicit=next((row["mapped_symbol"] for row in projection if row["date"]>=issued.isoformat()),None)
                # No defaultReturnValue, empty-map HasData or current IsDelisted
                # property can supply an identity when explicit rows disagree.
                if explicit!=ticker or mapping.GetMappedSymbol(at,"")!=ticker or mapping.HasData(at) is not True:_fail()
                identity=SecurityIdentifier.GenerateEquity(ticker,Market.USA,True,provider,at)
                if (not isinstance(identity,SecurityIdentifier) or identity.SecurityType!=SecurityType.Equity
                        or identity.Market!=Market.USA or _native_date(identity.Date)!=first
                        or identity.Symbol!=mapping.FirstTicker or not str(identity) or str(identity)==" 0"):_fail()
                sid=events._sid(str(identity));status="native_map_consistent_candidate"
                row_count=len(rows);row_hash=hashlib.sha256(events.canonical(projection)).hexdigest()
            except BaseException as error:
                if not isinstance(error,Exception):_stop(error)
                if type(error) in (AttributeError,TypeError,ImportError):
                    self._native_failure="unsupported_native_history_api";self._native=None
                    status=self._native_failure
                else:status="unsupported_ambiguous_or_missing_native_history"
                sid=None
        result=(sid,status,row_count,row_hash)
        receipt={"ticker":ticker,"issued_date":issued.isoformat(),"security_id":sid,"status":status,
            "native_map_rows":row_count,"native_map_rows_sha256":row_hash,
            "historical_identity_proven":False,"native_share_basis_proven":False}
        self._binding_chain=hashlib.sha256(bytes.fromhex(self._binding_chain)+events.canonical(receipt)).hexdigest()
        self._pending_receipts.append(receipt)
        self._binding_cache[key]=result
        return result,False

    def scores_for(self,decision_session,cutoff_utc,current_sids):
        """Private scores, states and census; current mapping VALUES are unused."""
        if not isinstance(current_sids,Mapping) and type(current_sids) not in (list,tuple,set,frozenset):_fail()
        inventory=tuple(current_sids)
        if len(inventory)>events.MAX_SECURITIES or len(set(inventory))!=len(inventory):_fail()
        for sid in inventory:events._sid(sid)
        decision=events._day(decision_session);cutoff=events._clock(cutoff_utc)
        if decision not in self._days:_fail()
        index=self._days.index(decision);local=cutoff.astimezone(ZoneInfo("America/New_York"))
        if not index or local.date()!=self._days[index-1] or local.time().replace(tzinfo=None)!=time(18):_fail()
        minimum=self._days[max(0,index-1-80-2)].isoformat();maximum=local.date().isoformat()
        selected=[];bindings={};counts=Counter();before=self._native_lookups
        for day in sorted(self._index):
            if not minimum<=day<=maximum:continue
            start,end,count=self._index[day]
            rows=json.loads(b"["+self._packet[start:end]+b"]")
            if type(rows) is not list or len(rows)!=count:_fail()
            for row in rows:
                row=events._event(row)
                group=_group_key(row)
                if group in self._conflicts:
                    row["source_refusals"]=sorted(set(row["source_refusals"])|{"conflicting_native_event_id"})
                    row["refusals"]=sorted(set(row["refusals"])|{"conflicting_native_event_id"})
                    row["state"],row["contribution"]="unavailable",None
                if row["event_key"] in self._inconsistent:
                    row["refusals"]=sorted(set(row["refusals"])|{"inconsistent_derived_event_metadata"})
                    row["state"],row["contribution"]="unavailable",None
                selected.append(row)
                issued=events._day(row["raw_issued_date"])
                eligible=bisect_right(self._days,issued)+1
                touched=events._clock(row["last_updated_utc"]) if row["last_updated_utc"] is not None else None
                if (row["ticker"] is None or touched is None or touched>cutoff or issued>local.date()
                        or eligible>=len(self._days) or self._opens[eligible]>cutoff or not 0<=index-1-eligible<=80):
                    counts["not_mapped_before_eligibility_or_update_cutoff"]+=1;continue
                (sid,status,_,_),cached=self._bind(row["ticker"],issued)
                bindings[row["event_key"]]=sid
                counts[status]+=1;counts["cache_hits"]+=cached
        report=events.score_bound_events(selected,sessions=list(self._sessions),decision_session=decision_session,
            cutoff_utc=cutoff_utc,security_id_by_event=bindings,security_ids=inventory)
        report["binding_census"]={"packet_source_rows":self._source_census["source_rows"],"window_loaded_rows":len(selected),
            "packet_rows_outside_loaded_window":self._source_census["source_rows"]-len(selected),
            "native_map_calls_this_decision":self._native_lookups-before,"native_map_calls_total":self._native_lookups,
            "statuses":dict(sorted(counts.items())),"global_conflicting_event_groups":len(self._conflicts),
            "binding_evidence_sha256":self._binding_chain,"pending_private_binding_receipts":len(self._pending_receipts),
            "native_binding_accepted":False,"native_share_basis_proven":False}
        report["score_scope"]="loaded_frozen_window_only_global_conflicts_retained"
        return report

    def drain_private_binding_receipts(self,maximum=200):
        """For the caller's PRIVATE journal only; never log this publicly.

        Contains event-ticker/date -> native SID/status/count/hash observations,
        no raw map/factor rows. Caller should retain bounded chunks after each
        decision; the cumulative digest remains in the safe aggregate census.
        """
        maximum=_bounded(maximum,200,1)
        result=self._pending_receipts[:maximum];del self._pending_receipts[:maximum]
        return json.loads(events.canonical(result))

    def public_summary(self):
        """Aggregate/hash/status metadata only; no event IDs, SIDs or map rows."""
        return {"schema":"tpr-cmp28-native-signal-summary-v1","study_id":events.STUDY,
            "packet_sha256":self._packet_sha256,"packet_bytes":len(self._packet),"encoding":"utf-8-json",
            "source_inventory_sha256":self._inventory_sha256,
            "source_census":json.loads(events.canonical(self._source_census)),"indexed_issued_dates":len(self._index),
            "global_conflicting_event_groups":len(self._conflicts),"inconsistent_versions":len(self._inconsistent),
            "native_map_calls":self._native_lookups,"cached_ticker_dates":len(self._binding_cache),
            "binding_evidence_sha256":self._binding_chain,"pending_private_binding_receipts":len(self._pending_receipts),
            "native_provider_status":"not_requested" if self._native is None and self._native_failure is None else self._native_failure or "typed_candidate_only",
            "historical_identity_proven":False,"native_share_basis_proven":False,"point_in_time_data":False,
            "rights_verified":False,"source_inputs_admitted":False,"canonical_admission":False}


def prepare_native_signals(packet_bytes,*,expected_sha256,expected_bytes,sessions,
        expected_source_inventory_sha256):
    """Pure exact plain-byte preparation; caller owns fresh private store read.

    No native provider is touched until scores_for reaches an eligible event.
    The whole plaintext hash and exact byte bound are checked BEFORE parsing.
    The retained packet/date offsets remain readable JSON, without binary codec
    imports, compression, dynamic import tricks or source-policy workarounds.
    """
    try:
        digest=_hash(expected_sha256);inventory=_hash(expected_source_inventory_sha256)
        size=_bounded(expected_bytes,MAX_PACKET_BYTES,1)
        if type(packet_bytes) is not bytes or len(packet_bytes)!=size or hashlib.sha256(packet_bytes).hexdigest()!=digest:_fail()
        return NativeSignals(packet_bytes,sessions,inventory)
    except BaseException as error:
        _stop(error)
