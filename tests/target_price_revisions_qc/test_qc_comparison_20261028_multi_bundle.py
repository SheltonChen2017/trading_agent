"""Pinned public sources + synthetic plain packet; no actual native/private IO."""
import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from types import ModuleType,SimpleNamespace as NS

import pytest

from research.target_price_revisions_qc import comparison_20261028_multi_bundle as b
from tests.target_price_revisions_qc import test_qc_comparison_20261028_algorithm as off_tests
from tests.target_price_revisions_qc import test_qc_comparison_20261028_multi_algorithm as multi_tests


@pytest.fixture(autouse=True)
def no_actual_effects(monkeypatch):
    import http.client
    from research.target_price_revisions_qc import extended_operations as operations
    def denied(*_args,**_kwargs):raise AssertionError("actual private/QC/provider/operator effect forbidden")
    monkeypatch.setattr(operations,"credential",denied)
    monkeypatch.setattr(operations,"read_private",denied)
    monkeypatch.setattr(operations.Operations,"__init__",denied)
    monkeypatch.setattr(http.client,"HTTPSConnection",denied)


@pytest.fixture
def sources():return {name:Path(name).read_bytes() for name in b.SOURCE_PATHS}


def synthetic_packet():
    return (json.dumps({"schema":"tpr-cmp28-derived-nominal-packet-v1","study_id":b.STUDY,
        "source_inventory_sha256":"c"*64,"events":[],"census":{"source_rows":0,"derived_rows":0,
        "unavailable_rows":0,"refusal_counts":{},"projection_count":0}},sort_keys=True,separators=(",",":"))+"\n").encode()


def descriptor():
    raw=synthetic_packet()
    return {"key":"tpr-cmp28/inputs/synthetic/packet.json","sha256":hashlib.sha256(raw).hexdigest(),
        "bytes":len(raw),"encoding":"utf-8-json","source_inventory_sha256":"c"*64}


def build(sources,**changes):
    args=dict(public_sources=sources,arm="cap_tilt_200",operation_id="TPR-CMP28-MULTI-SYNTHETIC-001",
        attempt=4,prior_attempts_looks_sha256="b"*64,signal_packet=descriptor())
    args.update(changes)
    return b.build_multi_candidate(**args)


def literal(raw,name):
    node=next(node for node in ast.parse(raw).body if isinstance(node,ast.Assign)
        and len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id==name)
    return ast.literal_eval(node.value)


@pytest.mark.parametrize("arm",tuple(b.ARMS))
def test_four_arms_have_one_shared_closed_config_and_consistent_source_hashes(sources,arm):
    original=deepcopy(sources);packet=descriptor();packet_before=deepcopy(packet)
    files,raw=build(sources,arm=arm,signal_packet=packet);report=json.loads(raw)
    assert sources==original and packet==packet_before
    assert len(files)==report["file_count"]==15
    assert report["maximum_combined_cloud_files"]==15+report["preserved_legacy_files"]==24
    assert "comparison_20261028_multi_config.py" not in files
    assert "comparison_20261028_bundle.py" not in files
    config_raw=literal(files["comparison_20261028_config.py"],"CONFIG_JSON");config=json.loads(config_raw)
    assert config["schema"]=="tpr-cmp28-multi-native-config-v1" and config["arm"]==arm
    assert config["candidate_id"]==b.ARMS[arm] and config["signal_packet"]==packet
    assert config["project_id"]==37650980 and config["attempt"]==4
    assert report["config_sha256"]==hashlib.sha256(config_raw.encode()).hexdigest()
    assert literal(files["comparison_20261028_multi_algorithm.py"],"EXPECTED_CONFIG_SHA256")==report["config_sha256"]
    assert literal(files["comparison_20261028_algorithm.py"],"EXPECTED_CONFIG_SHA256")!=report["config_sha256"]
    assert config["source_template_closure_sha256"]==report["source_template_closure_sha256"]
    assert report["template_source_hashes"]=={name:hashlib.sha256(raw).hexdigest() for name,raw in sources.items()}
    assert report["cloud_source_hashes"]=={name:hashlib.sha256(raw).hexdigest() for name,raw in files.items()}
    assert report["cloud_source_bytes"]=={name:len(raw) for name,raw in files.items()}
    hashes=json.dumps(report["cloud_source_hashes"],sort_keys=True,separators=(",",":")).encode()
    assert report["rendered_source_closure_sha256"]==hashlib.sha256(hashes).hexdigest()
    for key in ("predecessor_initialize_selected","off_initialize_selected","raw_development_identity_action_filters_shipped",
        "source_inputs_admitted","native_permission","qc_setup_complete","strategy_accepted","canonical_admission"):
        assert report[key] is False
    assert report["reservation_sha256"] is report["accepted_performance"] is None
    assert report["new_attempts"]==report["new_observed_looks"]==0


def test_all_flat_files_compile_without_package_or_compression_imports(sources):
    files,_=build(sources)
    for name,raw in files.items():
        tree=ast.parse(raw,filename=name);compile(tree,name,"exec");assert len(raw)<=60000
        assert not any(isinstance(node,ast.ImportFrom) and (node.level or (node.module or "").startswith("research.")) for node in ast.walk(tree))
        imports={node.module for node in ast.walk(tree) if isinstance(node,ast.ImportFrom)}
        imports|={item.name for node in ast.walk(tree) if isinstance(node,ast.Import) for item in node.names}
        assert not imports & {"gzip","zlib","codecs","extended_compressed_store"}
    tree=ast.parse(files["main.py"])
    assert len(tree.body)==2 and isinstance(tree.body[0],ast.Import) and isinstance(tree.body[1],ast.ClassDef)
    assert ast.unparse(tree.body[1].bases[0])=="candidate.ComparisonMultiAlgorithm"


def test_raw_revision_shipping_is_only_exact_numeric_date_calendar_helpers(sources):
    files,_=build(sources)
    module=ModuleType("synthetic_raw_helpers");exec(compile(files["raw_revision.py"],"<raw-helpers>","exec"),module.__dict__)
    assert module._number("10.00")[0]==10 and module._number(1.0)[0] is None
    assert module._native_id("native-ID-1") and module._ticker("ABC.A")
    assert module._calendar([{"session_date":"2021-01-04","open_utc":"2021-01-04T14:30:00Z"}])[0][0].isoformat()=="2021-01-04"
    for name in ("normalize_raw_revisions","_identity_map","_identity_reason","_action_exclusions",
        "STRICT_IDENTITY_POLICY","SHARADAR_IDENTITY_POLICY","STRICT_ACTION_POLICY","NOMINAL_ACTION_POLICY"):
        assert not hasattr(module,name)
    original=ast.parse(sources[b.RAW_PATH]);subset=ast.parse(files["raw_revision.py"])
    def nodes(tree):
        return {node.name:ast.dump(node,include_attributes=False) for node in tree.body if isinstance(node,(ast.FunctionDef,ast.ClassDef))}
    assert all(nodes(original)[name]==value for name,value in nodes(subset).items())


@pytest.mark.parametrize("path",tuple(b.PINS))
def test_every_independent_public_pin_refuses_even_one_newline(sources,path):
    sources[path]+=b"\n"
    with pytest.raises(b.MultiBundleRefusal):build(sources)


@pytest.mark.parametrize("change",[{"arm":"cap_off"},{"arm":"other"},{"arm":True},{"attempt":0},{"attempt":True},
    {"attempt":2**31},{"attempt":"4"},{"project_id":1},{"project_id":True},{"project_id":None},
    {"operation_id":"foreign"},{"operation_id":"TPR-CMP28-"},{"operation_id":"TPR-CMP28-a/b"},
    {"prior_attempts_looks_sha256":"0"*64}])
def test_wrong_arm_attempt_project_operation_or_history_refuses(sources,change):
    with pytest.raises(b.MultiBundleRefusal):build(sources,**change)


@pytest.mark.parametrize("field,value",[("key","tpr-cmp28/inputs/a/../x"),("key","private/other.json"),
    ("key","tpr-cmp28/inputs/a//b"),("bytes",True),("bytes",0),("bytes",512*1024**2+1),
    ("sha256","0"*64),("source_inventory_sha256","bad"),("encoding","gzip"),("gzip_bytes",10)])
def test_plain_packet_descriptor_is_closed_bounded_and_never_relabelled(sources,field,value):
    packet=descriptor();packet[field]=value
    with pytest.raises(b.MultiBundleRefusal):build(sources,signal_packet=packet)


@pytest.mark.parametrize("mode",["missing","extra","type","value"])
def test_exact_public_closure_refuses_arbitrary_source_or_private_input(sources,mode):
    if mode=="missing":sources.pop(next(iter(sources)))
    elif mode=="extra":sources["private/capture.json"]=b"{}"
    elif mode=="type":sources=list(sources.items())
    else:sources[next(iter(sources))]="source"
    with pytest.raises(b.MultiBundleRefusal):build(sources)


def load_flat(files,monkeypatch):
    off_tests.driver.__wrapped__(monkeypatch)
    monkeypatch.delitem(sys.modules,"extended_compressed_store",raising=False)
    names=["extended_loader","cap_tilt","cap_observer","extended_construction","extended_core",
        "extended_runtime_successor","extended_algorithm_successor","comparison_20261028",
        "comparison_20261028_config","comparison_20261028_algorithm","raw_revision","comparison_20261028_events",
        "comparison_20261028_signal_native","comparison_20261028_multi_algorithm","main"]
    modules={name:ModuleType(name) for name in names}
    for name,module in modules.items():monkeypatch.setitem(sys.modules,name,module)
    for name in names:exec(compile(files[name+".py"],"<flat-"+name+">","exec"),modules[name].__dict__)
    modules["comparison_20261028_multi_algorithm"].previous=modules["comparison_20261028_algorithm"]
    return modules


def setup_native_stubs(module,packet):
    algo=module.ComparisonMultiAlgorithm();algo.live_mode=False;algo.project_id=37650980;algo.algorithm_id=""
    algo.get_locked=lambda:False;algo._initialized_factor_provider=lambda:object()
    reads=[];algo.object_store=NS(read_bytes=lambda key:(reads.append(key) or packet))
    for name in ("set_start_date","set_end_date","set_time_zone","set_account_currency","set_cash","set_warm_up","set_benchmark"):
        setattr(algo,name,lambda *_:None)
    algo.add_chart=lambda *_:None;algo.universe_settings=NS();algo.add_security_initializer=lambda *_:None
    labels=[];universes=[]
    algo.add_equity=lambda label,*args,**kwargs:(labels.append(label) or NS(symbol=off_tests.Symbol("ETF-"+label,label)))
    algo.universe=NS(etf=lambda symbol,universe_filter_func:NS(symbol=off_tests.Symbol("CTX-"+symbol.id),filter=universe_filter_func))
    def add_universe(value):
        if callable(value):value=NS(symbol=off_tests.Symbol("CTX-FUNDAMENTAL"),filter=value)
        universes.append(value);return value
    algo.add_universe=add_universe;algo.date_rules=NS(every_day=lambda symbol:None)
    algo.time_rules=NS(at=lambda *_:None);algo.schedule=NS(on=lambda *_:None)
    return algo,reads,labels,universes


@pytest.mark.parametrize("arm",tuple(b.ARMS))
def test_real_flat_modules_initialize_each_arm_with_exact_plain_packet_and_no_native_lookup(sources,monkeypatch,arm):
    files,report=build(sources,arm=arm);report=json.loads(report);modules=load_flat(files,monkeypatch)
    module=modules["comparison_20261028_multi_algorithm"];main=modules["main"]
    assert issubclass(main.Main,module.ComparisonMultiAlgorithm)
    assert [name for name,value in main.__dict__.items() if isinstance(value,type)]==["Main"]
    algo,reads,labels,universes=setup_native_stubs(module,synthetic_packet());algo.initialize()
    assert reads==[descriptor()["key"]] and labels==list(module.SLEEVES) and len(universes)==7
    assert algo._config["arm"]==arm and algo._config["source_template_closure_sha256"]==report["source_template_closure_sha256"]
    summary=algo._signal_provider.public_summary()
    assert summary["native_provider_status"]=="not_requested" and summary["source_census"]["source_rows"]==0
    assert algo._signal_provider._packet==synthetic_packet()
    assert modules["cap_tilt"].ETFS==("SPY","XLV","XLE","QQQ","SOXX","REMX")
    assert module.SLEEVES==("SPY","XLE","REMX","KIE","XLF","IWM")


def test_flat_composition_keeps_zero_donor_and_held_exit_without_clipping(sources,monkeypatch):
    files,_=build(sources);modules=load_flat(files,monkeypatch)
    multi_tests.test_all_zero_selected_donor_remains_in_evidence_and_held_position_exits(modules["comparison_20261028_multi_algorithm"])


def test_renderer_has_only_public_pure_helpers_and_no_effect_calls():
    tree=ast.parse(Path(b.__file__).read_text())
    imports={node.module for node in ast.walk(tree) if isinstance(node,ast.ImportFrom)}
    imports|={item.name for node in ast.walk(tree) if isinstance(node,ast.Import) for item in node.names}
    assert imports<={"__future__","ast","hashlib","json","re",None}
    calls={node.func.id for node in ast.walk(tree) if isinstance(node,ast.Call) and isinstance(node.func,ast.Name)}
    assert not calls & {"open","exec","eval","__import__"}
