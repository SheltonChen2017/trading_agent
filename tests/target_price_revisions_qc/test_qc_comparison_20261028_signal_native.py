"""Native signal software only: synthetic packet, typed map stubs, no I/O."""
from copy import deepcopy
from datetime import date,datetime,time
from decimal import Decimal
import gzip
import hashlib
import json
from pathlib import Path
import sys
from types import ModuleType,SimpleNamespace as NS

import pytest
from research.target_price_revisions_qc import comparison_20261028_signal_native as n
from tests.target_price_revisions_qc import test_qc_comparison_20261028_events as fixture


@pytest.fixture(scope="module")
def sessions():
    return fixture.sessions.__wrapped__()


def packet(rows):
    source=fixture.project(rows)
    body={"schema":"tpr-cmp28-derived-nominal-packet-v1","study_id":n.events.STUDY,
        "source_inventory_sha256":"a"*64,"events":source["events"],"census":{
            "source_rows":source["census"]["source_rows"],"derived_rows":source["census"]["derived_rows"],
            "unavailable_rows":source["census"]["unavailable_rows"],"refusal_counts":source["census"]["refusal_counts"],"projection_count":1}}
    return body


def arguments(body,sessions):
    plain=n.events.canonical(body)
    return dict(packet_bytes=plain,expected_sha256=hashlib.sha256(plain).hexdigest(),expected_bytes=len(plain),
        expected_source_inventory_sha256="a"*64,sessions=sessions)


def prepare(rows,sessions):return n.prepare_native_signals(**arguments(packet(rows),sessions))


def cutoff(day="2020-12-31"):return day+"T23:00:00Z"


class MapRow:
    def __init__(self,day,ticker,mode=None):self.Date=datetime.fromisoformat(day);self.MappedSymbol=ticker;self.DataMappingMode=mode


class MapFile(list):
    def __init__(self,permtick,rows):
        super().__init__(rows);self.Permtick=permtick
        self.FirstDate=self[0].Date if self else datetime(1900,1,1)
        self.DelistingDate=self[-1].Date if self else datetime(2050,1,1)
        self.FirstTicker=self[0].MappedSymbol if self else permtick
    def GetMappedSymbol(self,at,default=""):
        return next((row.MappedSymbol for row in self if row.Date>=at),default)
    def HasData(self,at):return not self or self.FirstDate<=at<=self.DelistingDate
    @property
    def IsDelisted(self):raise AssertionError("current delisting filter forbidden")


class Resolver:
    def __init__(self,files):self.files=files;self.calls=[];self.override=None
    def ResolveMapFile(self,ticker,at):
        self.calls.append((ticker,at))
        if self.override is not None:return self.override
        return next((item for item in self.files if item.HasData(at) and item.GetMappedSymbol(at,"")==ticker),MapFile(ticker,[]))


class Provider:
    def __init__(self,resolver):self.resolver=resolver;self.calls=[]
    def Get(self,key):self.calls.append(key);return self.resolver


class Identifier:
    def __init__(self,ticker,day,*,market="usa",kind="equity"):
        self.Symbol=ticker;self.Date=day;self.SecurityType=kind;self.Market=market
    def __str__(self):return self.Symbol+"-SID-"+self.Date.strftime("%Y%m%d")


@pytest.fixture
def native(monkeypatch):
    old=MapFile("A.OLD",[MapRow("2010-01-01","A"),MapRow("2022-01-01","A")])
    newer=MapFile("A.NEW",[MapRow("2023-01-01","A"),MapRow("2050-01-01","A")])
    resolver=Resolver([old,newer]);provider=Provider(resolver)
    state=NS(parts=0,generate=[],bad_sid=None)
    class Parts:
        def __getitem__(self,kind):
            def get():state.parts+=1;return [provider]
            return get
    class NativeID(Identifier):
        @staticmethod
        def GenerateEquity(ticker,market,map_symbol,provided,at):
            state.generate.append((ticker,market,map_symbol,provided,at))
            if state.bad_sid is not None:return state.bad_sid
            found=provided.Get("generated").ResolveMapFile(ticker,at)
            return NativeID(found.FirstTicker,found.FirstDate)
    root=ModuleType("QuantConnect");root.SecurityIdentifier=NativeID;root.SecurityType=NS(Equity="equity");root.Market=NS(USA="usa")
    interfaces=ModuleType("QuantConnect.Interfaces");interfaces.IMapFileProvider=Provider
    util=ModuleType("QuantConnect.Util");util.Composer=NS(Instance=NS(GetParts=Parts()))
    auxiliary=ModuleType("QuantConnect.Data.Auxiliary")
    auxiliary.AuxiliaryDataKey=NS(EquityUsa=object());auxiliary.MapFileResolver=Resolver
    auxiliary.MapFile=MapFile;auxiliary.MapFileRow=MapRow
    for module in (root,interfaces,util,auxiliary):monkeypatch.setitem(sys.modules,module.__name__,module)
    return NS(state=state,provider=provider,resolver=resolver,old=old,newer=newer,NativeID=NativeID)


def test_prepare_proves_exact_plain_bytes_then_indexes_without_any_native_lookup(sessions,native):
    signals=prepare([fixture.rating()],sessions)
    summary=signals.public_summary()
    assert summary["source_census"]["source_rows"]==1 and summary["indexed_issued_dates"]==1
    assert summary["native_provider_status"]=="not_requested" and native.state.parts==0
    assert native.resolver.calls==[] and native.state.generate==[]
    wire=n.events.canonical(summary)
    assert b"A-SID" not in wire and b"mapped_symbol" not in wire and b"price_target" not in wire
    assert summary["historical_identity_proven"] is summary["source_inputs_admitted"] is False


def test_actual_fixed_native_historical_overload_binds_old_delisted_identity_by_issued_date(sessions,native):
    signals=prepare([fixture.rating()],sessions)
    report=signals.scores_for("2021-01-04",cutoff(),{"A-SID-20100101":object()})
    assert Decimal(report["scores_by_sid"]["A-SID-20100101"]["value"])==Decimal("0.1")
    assert native.state.generate[0]==("A","usa",True,native.provider,datetime(2020,12,29))
    assert native.state.parts==1
    assert report["binding_census"]["statuses"]["native_map_consistent_candidate"]==1
    assert report["binding_census"]["native_binding_accepted"] is False
    # Repeated scoring reuses the native ticker/date candidate, never today's alias.
    before=len(native.state.generate);signals.scores_for("2021-01-04",cutoff(),["A-SID-20100101"])
    assert len(native.state.generate)==before


def test_ticker_reuse_resolves_two_distinct_permanent_sids_at_the_two_event_dates(sessions,native):
    first=fixture.project([fixture.rating()])["events"]
    late=fixture.page([fixture.rating("LATE",day="2025-01-02")],window=["2025-01-01","2025-01-31"])
    later=n.events.project_page(**fixture.arguments(late,request=2,window=["2025-01-01","2025-01-31"]))["events"]
    body=packet([fixture.rating()]);body["events"]+=later
    body["census"].update(source_rows=2,derived_rows=2,projection_count=2)
    signals=n.prepare_native_signals(**arguments(body,sessions))
    early=signals.scores_for("2021-01-04",cutoff(),["A-SID-20100101","A-SID-20230101"])
    assert early["scores_by_sid"]["A-SID-20230101"]["value"] is None
    assert all(call[-1].year==2020 for call in native.state.generate)
    late_report=signals.scores_for("2025-01-06",cutoff("2025-01-03"),["A-SID-20100101","A-SID-20230101"])
    assert late_report["scores_by_sid"]["A-SID-20230101"]["value"] is None # Jan02 second later openJan06 is afterFriday cutoff.
    next_report=signals.scores_for("2025-01-07",cutoff("2025-01-06"),["A-SID-20100101","A-SID-20230101"])
    assert next_report["scores_by_sid"]["A-SID-20230101"]["value"] is not None
    assert native.state.generate[-1][-1]==datetime(2025,1,2)


@pytest.mark.parametrize("changes",[{"last_updated":"2025-01-01T12:00:00Z"},{"date":"2020-12-30","last_updated":"2020-12-30T12:00:00Z"}])
def test_future_updated_or_not_yet_eligible_event_never_reaches_native_lookup(sessions,native,changes):
    signals=prepare([fixture.rating(**changes)],sessions)
    report=signals.scores_for("2021-01-04",cutoff(),["A-SID-20100101"])
    assert report["scores_by_sid"]["A-SID-20100101"]["value"] is None
    assert native.state.parts==0 and native.state.generate==[] and native.resolver.calls==[]


@pytest.mark.parametrize("fault",["empty","untyped","duplicate_date","future_first","already_delisted_at_issue","wrong_ticker","mapping_mode","bad_sid_date","bad_sid_market"])
def test_native_map_ambiguity_defaults_and_inconsistent_sid_are_unknown_not_zero(sessions,native,fault):
    if fault=="empty":native.resolver.override=MapFile("A",[])
    elif fault=="untyped":native.resolver.override=[]
    elif fault=="duplicate_date":native.old.append(MapRow("2022-01-01","A"))
    elif fault=="future_first":native.old.FirstDate=datetime(2021,1,1)
    elif fault=="already_delisted_at_issue":native.old.DelistingDate=datetime(2019,1,1)
    elif fault=="wrong_ticker":native.old[1].MappedSymbol="WRONG";native.resolver.override=native.old
    elif fault=="mapping_mode":native.old[0].DataMappingMode=0
    elif fault=="bad_sid_date":native.state.bad_sid=native.NativeID("A",datetime(2000,1,1))
    else:native.state.bad_sid=native.NativeID("A",datetime(2010,1,1),market="canada")
    signals=prepare([fixture.rating()],sessions)
    report=signals.scores_for("2021-01-04",cutoff(),["A-SID-20100101"])
    assert report["scores_by_sid"]["A-SID-20100101"]=={"state":"unknown","value":None}
    assert report["binding_census"]["statuses"]["unsupported_ambiguous_or_missing_native_history"]==1


def test_global_conflict_in_future_window_stays_unknown_in_past_window_without_future_map_lookup(sessions,native):
    body=packet([fixture.rating()])
    later=fixture.page([fixture.wrapped(fixture.rating(day="2025-01-02",price_target="12"),conflict=True)],window=["2025-01-01","2025-01-31"])
    projected=n.events.project_page(**fixture.arguments(later,request=2,window=["2025-01-01","2025-01-31"]))
    body["events"]+=projected["events"]
    body["census"].update(source_rows=2,unavailable_rows=1,projection_count=2,refusal_counts={"conflicting_native_event_id":1})
    signals=n.prepare_native_signals(**arguments(body,sessions))
    report=signals.scores_for("2021-01-04",cutoff(),["A-SID-20100101"])
    assert report["scores_by_sid"]["A-SID-20100101"]["value"] is None
    assert report["binding_census"]["global_conflicting_event_groups"]==1
    assert report["binding_census"]["window_loaded_rows"]==1
    assert all(call[-1].year==2020 for call in native.state.generate)


@pytest.mark.parametrize("fault",["hash","bytes","wrong_type","zero","over_bound"])
def test_plain_identity_gates_precede_json_parse_or_native_lookup(sessions,native,monkeypatch,fault):
    args=arguments(packet([fixture.rating()]),sessions)
    if fault=="hash":args["expected_sha256"]="b"*64
    elif fault=="bytes":args["expected_bytes"]+=1
    elif fault=="wrong_type":args["packet_bytes"]=bytearray(args["packet_bytes"])
    elif fault=="zero":args["expected_bytes"]=0
    else:args["expected_bytes"]=n.MAX_PACKET_BYTES+1
    monkeypatch.setattr(n,"_JSONStream",lambda *_:pytest.fail("identity gate must precede parse"))
    with pytest.raises(n.NativeSignalError):n.prepare_native_signals(**args)
    assert native.state.parts==0


def test_compressed_input_is_not_an_alternate_native_format(sessions,native):
    args=arguments(packet([fixture.rating()]),sessions)
    encoded=gzip.compress(args["packet_bytes"],mtime=0)
    args.update(packet_bytes=encoded,expected_bytes=len(encoded),expected_sha256=hashlib.sha256(encoded).hexdigest())
    with pytest.raises(n.NativeSignalError):n.prepare_native_signals(**args)
    assert native.state.parts==0


@pytest.mark.parametrize("fault",["schema","study","inventory","census_count","unknown","future_order","event_acceptance"])
def test_closed_packet_schema_and_full_source_census_are_required(sessions,fault):
    body=packet([fixture.rating()])
    if fault=="schema":body["schema"]="foreign"
    elif fault=="study":body["study_id"]="foreign"
    elif fault=="inventory":body["source_inventory_sha256"]="b"*64
    elif fault=="census_count":body["census"]["source_rows"]=2
    elif fault=="unknown":body["secret"]="PRIVATE-SENTINEL"
    elif fault=="event_acceptance":body["events"][0]["historical_identity_proven"]=True
    else:body["events"]*=2;body["events"][0]["raw_issued_date"]="2020-12-30"
    with pytest.raises(n.NativeSignalError) as caught:n.prepare_native_signals(**arguments(body,sessions))
    assert "PRIVATE-SENTINEL" not in str(caught.value)


def test_hash_bound_packet_is_indexed_by_date_not_kept_as_a_complete_json_tree(sessions):
    signals=prepare([fixture.rating()],sessions)
    assert not hasattr(signals,"events")
    assert all(all(type(item) is int for item in value) for value in signals._index.values())
    assert all(0<=value[0]<value[1]<=len(signals._packet) for value in signals._index.values())
    assert signals.public_summary()["encoding"]=="utf-8-json"
    assert signals.public_summary()["source_census"]["derived_rows"]==1


@pytest.mark.parametrize("fault",["array_trailing_comma","root_trailing_comma","trailing_object","duplicate_field","float_count","bool_refusal_count"])
def test_streaming_plain_json_is_strict_and_body_free(sessions,fault):
    body=packet([fixture.rating(price_target=None)])
    args=arguments(body,sessions);plain=args["packet_bytes"]
    if fault=="array_trailing_comma":
        marker=b'],"schema"';assert marker in plain;plain=plain.replace(marker,b',],"schema"',1)
    elif fault=="root_trailing_comma":plain=plain.rstrip()[:-1]+b',}'
    elif fault=="trailing_object":plain+=b'{}'
    elif fault=="duplicate_field":plain=plain.rstrip()[:-1]+b',"schema":"PRIVATE-SENTINEL"}'
    elif fault=="float_count":plain=plain.replace(b'"source_rows":1',b'"source_rows":1.0',1)
    else:plain=plain.replace(b'"invalid_positive_target":1',b'"invalid_positive_target":true',1)
    args.update(packet_bytes=plain,expected_bytes=len(plain),expected_sha256=hashlib.sha256(plain).hexdigest())
    with pytest.raises(n.NativeSignalError) as caught:n.prepare_native_signals(**args)
    assert "PRIVATE-SENTINEL" not in str(caught.value)


def test_uploaded_provider_has_no_compression_encoding_dynamic_import_or_file_openers():
    import ast
    tree=ast.parse(Path(n.__file__).read_bytes())
    modules=[]
    for node in ast.walk(tree):
        if isinstance(node,ast.Import):modules.extend(alias.name.split('.')[0] for alias in node.names)
        elif isinstance(node,ast.ImportFrom) and node.module:modules.append(node.module.split('.')[0])
    assert not set(modules)&{"gzip","zlib","base64","codecs","bz2","lzma","requests","http","socket","os","pathlib"}
    calls={node.func.id for node in ast.walk(tree) if isinstance(node,ast.Call) and isinstance(node.func,ast.Name)}
    assert not calls&{"open","eval","exec","compile","__import__"}


def test_unsupported_native_overload_is_not_retried_unchanged_for_every_event(sessions,native,monkeypatch):
    def unsupported(*args):raise TypeError("PRIVATE-SENTINEL unsupported overload")
    monkeypatch.setattr(native.NativeID,"GenerateEquity",unsupported)
    signals=prepare([
        fixture.rating("E2",day="2020-12-28",last_updated="2020-12-28T12:00:00Z"),fixture.rating()],sessions)
    report=signals.scores_for("2021-01-04",cutoff(),["A-SID-20100101"])
    assert report["scores_by_sid"]["A-SID-20100101"]["value"] is None
    assert signals.public_summary()["native_provider_status"]=="unsupported_native_history_api"
    assert report["binding_census"]["native_map_calls_this_decision"]==1
    assert "PRIVATE-SENTINEL" not in n.events.canonical(signals.public_summary()).decode()


def test_private_binding_receipts_are_bounded_and_safe_summary_contains_only_their_digest(sessions,native):
    signals=prepare([fixture.rating()],sessions)
    result=signals.scores_for("2021-01-04",cutoff(),["A-SID-20100101"])
    receipts=signals.drain_private_binding_receipts()
    assert len(receipts)==1 and receipts[0]["security_id"]=="A-SID-20100101"
    assert receipts[0]["native_map_rows"]==2 and receipts[0]["native_map_rows_sha256"]
    assert "mapped_symbol" not in n.events.canonical(receipts).decode()
    assert signals.drain_private_binding_receipts()==[]
    summary=signals.public_summary()
    assert result["binding_census"]["binding_evidence_sha256"]==summary["binding_evidence_sha256"]
    assert "A-SID" not in n.events.canonical(summary).decode()
    with pytest.raises(n.NativeSignalError):signals.drain_private_binding_receipts(201)


def test_utf8_packet_uses_byte_offsets_without_a_codec_package(sessions,native):
    body=packet([fixture.rating()])
    body["events"][0]["state"]="unavailable";body["events"][0]["contribution"]=None
    body["events"][0]["refusals"]=["unknown_évidence"]
    body["census"].update(derived_rows=0,unavailable_rows=1,refusal_counts={"unknown_évidence":1})
    args=arguments(body,sessions)
    plain=json.dumps(body,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode("utf-8")
    args.update(packet_bytes=plain,expected_bytes=len(plain),expected_sha256=hashlib.sha256(plain).hexdigest())
    signals=n.prepare_native_signals(**args)
    report=signals.scores_for("2021-01-04",cutoff(),["A-SID-20100101"])
    assert report["scores_by_sid"]["A-SID-20100101"]["value"] is None
    assert report["census"]["static_refusal_counts"]=={"unknown_évidence":1}


def test_large_plain_packet_crosses_token_blocks_and_reuses_one_native_date_binding(sessions,native):
    rows=[fixture.rating("E"+str(index)) for index in range(1000)]
    args=arguments(packet(rows),sessions)
    assert len(args["packet_bytes"])>n.BLOCK*4
    signals=n.prepare_native_signals(**args)
    report=signals.scores_for("2021-01-04",cutoff(),["A-SID-20100101"])
    assert Decimal(report["scores_by_sid"]["A-SID-20100101"]["value"])==Decimal("0.1")
    assert report["binding_census"]["window_loaded_rows"]==1000
    assert len(native.state.generate)==1 and signals._index["2020-12-29"][2]==1000


@pytest.mark.parametrize("mutation",["today_instead_of_event_date","map_future_updated_event","omit_whole_packet_hash"])
def test_semantic_in_memory_mutants_are_killed_without_disk_source_changes(sessions,native,monkeypatch,mutation):
    original=n
    source=Path(original.__file__).read_text()
    if mutation=="today_instead_of_event_date":
        before="GenerateEquity(ticker,Market.USA,True,provider,at)"
        after="GenerateEquity(ticker,Market.USA,True,provider,datetime(2026,10,28))"
    elif mutation=="map_future_updated_event":
        before=" or touched>cutoff";after=""
    else:
        before=" or hashlib.sha256(packet_bytes).hexdigest()!=digest";after=""
    assert source.count(before)==1
    mutant=ModuleType(original.__name__+"_synthetic_mutant")
    mutant.__package__=original.__package__
    exec(compile(source.replace(before,after,1),"<synthetic-native-signal-mutant>","exec"),mutant.__dict__)
    with monkeypatch.context() as patch:
        patch.setitem(globals(),"n",mutant)
        with pytest.raises((AssertionError,TypeError,pytest.fail.Exception)):
            if mutation=="today_instead_of_event_date":
                test_actual_fixed_native_historical_overload_binds_old_delisted_identity_by_issued_date(sessions,native)
            elif mutation=="map_future_updated_event":
                test_future_updated_or_not_yet_eligible_event_never_reaches_native_lookup(sessions,native,{"last_updated":"2025-01-01T12:00:00Z"})
            else:
                args=arguments(packet([fixture.rating()]),sessions)
                args["expected_sha256"]="b"*64
                with pytest.raises(mutant.NativeSignalError):mutant.prepare_native_signals(**args)
    assert Path(original.__file__).read_text()==source
