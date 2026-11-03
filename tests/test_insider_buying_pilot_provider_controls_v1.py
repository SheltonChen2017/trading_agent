"""Invented retained roots only, under the process-tree native test fence."""
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import stat

import pytest

pytest.importorskip("fcntl", reason="supported macOS/POSIX retained custody")
from data.hashing import hash_payload
from research import insider_buying_pilot_provider_controls_v1 as m
from research import insider_buying_sec_2006q1_parent_bootstrap as fixture_bootstrap


class Memory:
    def __init__(self): self.checks = 0
    def check(self): self.checks += 1


def _helper(name):
    path = Path(__file__).with_name(name)
    spec = importlib.util.spec_from_file_location("invented_provider_control_"+path.stem, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def selected(tmp_path_factory):
    helper = _helper("test_insider_buying_pilot_sec_required21_selection_v1.py")
    # The OS denies all actual artifact reads, including stat. Invented
    # factory construction must not enumerate legacy real-root aliases.
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(fixture_bootstrap, "actual_roots", lambda: ())
        return helper._fixture_selection(helper.corpus.__wrapped__(tmp_path_factory))


@pytest.fixture(autouse=True)
def invented_legacy_root_inventory(monkeypatch):
    monkeypatch.setattr(fixture_bootstrap, "actual_roots", lambda: ())


def _put(root, name, raw):
    path = root/name; path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_bytes(raw); path.chmod(0o600)
    return len(raw), m._sha(raw)


def _recent(root, helper):
    root.mkdir(mode=0o700)
    candidates, filings = [], []
    masters = [{"period": p, "receipt": {"source_sha256": str(i+1)*64, "receipt_sha256": str(i+3)*64}}
        for i,p in enumerate(("2022Q4", "2023Q1"))]
    for i, accession in enumerate(m.recent.FIXED_ACCESSIONS):
        period = "2022Q4" if i<8 else "2023Q1"; day = "2022-11-17" if i<8 else "2023-02-06"
        form = "4" if i%8<6 else "4/A"; issuer = "0000123456"
        candidate = {k:"a"*64 for k in m.recent._CANDIDATE_KEYS}
        candidate.update(period=period,accession_number=accession,form_type=form,filing_date=day,filing_date_raw=day,issuer_cik=issuer)
        request = {"period":period,"accession_number":accession,"form_type":form,"filing_date":day,
            "issuer_cik":issuer,"url":"https://www.sec.gov/Archives/edgar/data/9999999/"+accession+".txt",
            "master_decoded_sha256":masters[0 if i<8 else 1]["receipt"]["source_sha256"]}
        raw = helper._body(request).replace(b"</issuer>", b"<issuerTradingSymbol>INVENTED-PRIVATE</issuerTradingSymbol></issuer>")
        target = m._target(request); projected = m.project_sec_complete_submission(target,raw).to_payload()
        relative = "objects/"+m._sha(raw)+".bin"; _put(root,relative,raw)
        filings.append({"candidate":candidate,"status":"acquired_noncanonical","reason":None,"source_url":request["url"],
            "index_receipt_sha256":masters[0 if i<8 else 1]["receipt"]["receipt_sha256"],
            "raw_object":{"relative_path":relative,"sha256":m._sha(raw),"size_bytes":len(raw)},"projection":projected})
        candidates.append(candidate)
    inventory_sha = hash_payload(candidates)
    inventory={"kind":"sec-complete-frozen-inventory","version":m.recent._ACQUISITION_VERSION,
        "code_commit":m.recent.CAPTURE_CODE_COMMIT,"inventory_sha256":inventory_sha,"candidates":candidates,
        "quarter_master_urls":m.recent._MASTER_URLS,"owner_selected_sixteen":False,"source_authenticated":False,
        "canonical_evidence":False,"research_looks":0}
    report={k:False for k in m.recent._REPORT_KEYS}
    report.update(kind=m.recent._ACQUISITION_VERSION,inventory_sha256=inventory_sha,capture_git_commit_verified=m.recent.CAPTURE_CODE_COMMIT,
        master_indexes=masters,filings=filings,attempt_count=18,distinct_artifact_count=18,halted_reason=None,
        complete_sample_acquired=True,research_looks=0,authorized_outcome_looks=0,consumed_outcome_looks=0,
        attempt_journal={"sha256":"9"*64})
    report_raw=m._raw(report)+b"\n"
    pins={"inventory.json":_put(root,"inventory.json",m._raw(inventory)+b"\n"),m.RECENT_REPORT:_put(root,m.RECENT_REPORT,report_raw)}
    _put(root,"commit.json",m._raw({"kind":"sec-complete-commit","report_name":m.RECENT_REPORT,
        "report_sha256":m._sha(report_raw),"attempt_journal_sha256":"9"*64})+b"\n")
    return pins


@pytest.fixture
def roots(selected,tmp_path):
    helper = _helper("test_insider_buying_pilot_sec_required21_capture_v1.py")
    result, warm, calls, clock=helper._run(selected,tmp_path)
    recent=tmp_path/"invented-recent"
    recent_pins=_recent(recent,helper)
    warm_pins={name:(len((warm/name).read_bytes()),m._sha((warm/name).read_bytes())) for name in m.WARM_PINS}
    return warm,recent,warm_pins,recent_pins


def _metadata(roots):
    wr,rr,wp,rp=roots
    return m.metadata_invented(wr,rr,warm_pins=wp,recent_pins=rp,memory=Memory())


def test_two_stage_complete_invented_controls_and_public_privacy(roots):
    value=_metadata(roots)
    assert value["fixture_only"] is True and len(value["selected"])==12
    assert len(m._raw(value))<=m.MAX_METADATA
    assert [v["ordinal"] for v in value["selected"][8:]]==[0,5,8,14]
    assert [v["target"]["form_type"] for v in value["selected"][8:]]==["4","4","4","4/A"]
    assert len(m.body_paths(value))==54 and len(value["warm_readback_leaves"])==47
    result=m.derive_invented(value,warm_pins=roots[2],recent_pins=roots[3],memory=Memory())
    assert len(result["cases"])==12 and len(result["source_pins"])==54
    assert all(set(v)==m._CASE_KEYS for v in result["cases"])
    assert all(set(v)=={"case_id","cik","accession","form_type","filing_date","acceptance_digits","source_symbol","body_sha256"} for v in result["cases"])
    assert all(len(v["cik"])==10 and len(v["accession"])==18 and len(v["acceptance_digits"])==14 for v in result["cases"])
    assert result["cases"][8]["cik"]=="0000123456"
    assert result["cases"][8]["accession"].startswith("0000002178")
    assert result["cases"][8]["source_symbol"]=="INVENTED-PRIVATE"
    from research import insider_buying_pilot_fmp_eod_qualification_v1 as capture
    from research import insider_buying_pilot_fmp_eod_projection_v1 as projection
    assert capture._case_list(result["cases"])==result["cases"]
    assert projection._cases(result["cases"])==result["cases"]
    assert result["recent_full16_replayed"] is False and result["warmup_full_readback_verified"] is True
    public=m.public_summary(result); wire=m._raw(public)
    for marker in (b"INVENTED-PRIVATE",b"0000123456",b"accession18",b"body_path",str(roots[0]).encode()):
        assert marker not in wire
    assert public["control_count"]==12 and public["authority"]["backtesting_ready"] is False
    assert all(v is False if type(v)is bool else v==0 for v in result["authority"].values())


def test_metadata_stage_opens_no_originals(roots,monkeypatch):
    opened=[]; original=m._Hold.read
    def read(self,relative,**kwargs):
        assert not relative.startswith("objects/")
        opened.append(relative);return original(self,relative,**kwargs)
    monkeypatch.setattr(m._Hold,"read",read)
    value=_metadata(roots)
    assert len(value["source_pins"])==16 and all(not p.endswith(".bin") for p in value["source_pins"])


def test_detached_actual_allowlist_is_exact49_plus_seven_without_opening_inputs(roots,monkeypatch):
    value=_metadata(roots);oldwarm,oldrecent=value["warm_root"],value["recent_root"]
    value["fixture_only"]=False;value["warm_root"]=str(m.WARM_ROOT);value["recent_root"]=str(m.RECENT_ROOT)
    for i,row in enumerate(value["selected"]):
        row["body_path"]=str((m.WARM_ROOT if i<8 else m.RECENT_ROOT)/"objects"/(row["body_pin"]["sha256"]+".bin"))
        if i<8:row["target"].update(period="2020Q4",filing_date="2020-10-01")
    value["warm_readback_leaves"]=m._warm_leaves(value["selected"],fixture=False)
    value["source_pins"]={p.replace(oldwarm,str(m.WARM_ROOT)).replace(oldrecent,str(m.RECENT_ROOT)):v for p,v in value["source_pins"].items()}
    monkeypatch.setattr(m,"_Hold",lambda *a:pytest.fail("detached allowlist opened an input"))
    paths=m.body_paths(value)
    assert len(paths)==56 and len([p for p in paths if p.is_relative_to(m.WARM_ROOT)])==49
    assert m.WARM_ROOT/"selection-started.json" in paths and m.WARM_ROOT/"selection-complete.json" in paths
    changed=deepcopy(value);changed["warm_readback_leaves"][0]="arbitrary-secret.json"
    with pytest.raises(m.ProviderControlsError):m.body_paths(changed)


def test_full_warmup_readback_is_load_bearing_for_unchanged_unselected_controls(roots):
    value=_metadata(roots);path=roots[0]/"request-000-headers.json"
    control=json.loads(path.read_bytes())
    control["headers"]=[[name,"1" if name=="Content-Length" else val] for name,val in control["headers"]]
    path.write_bytes(m._raw(control))
    with pytest.raises(m.ProviderControlsError,match="body_refused"):
        m.derive_invented(value,warm_pins=roots[2],recent_pins=roots[3],memory=Memory())


@pytest.mark.parametrize("kind",["plan","result","report","inventory"])
def test_external_pin_precedes_decoding(roots,monkeypatch,kind):
    root,name=(roots[0],"plan.json") if kind=="plan" else (roots[0],"request-000-result.json") if kind=="result" else (roots[1],m.RECENT_REPORT if kind=="report" else "inventory.json")
    path=root/name;raw=path.read_bytes();path.write_bytes(raw.replace(b'"',b"'",1))
    with pytest.raises(m.ProviderControlsError,match="external_pin_refused"):_metadata(roots)


@pytest.mark.parametrize("kind",["path","sha","count","case_id","ordinal","authority","fixture"])
def test_metadata_rebinding_cannot_become_actual_controls(roots,kind):
    value=_metadata(roots);changed=deepcopy(value)
    if kind=="path":changed["selected"][0]["body_path"]="/etc/passwd"
    elif kind=="sha":changed["selected"][0]["body_pin"]["sha256"]="0"*64
    elif kind=="count":changed["selected"].pop()
    elif kind=="case_id":changed["selected"][0]["case_id"]="recent-01"
    elif kind=="ordinal":changed["selected"][8]["ordinal"]=1
    elif kind=="authority":changed["authority"]["backtesting_ready"]=True
    else:changed["fixture_only"]=False
    with pytest.raises((m.ProviderControlsError,ValueError,KeyError)):
        m.derive_invented(changed,warm_pins=roots[2],recent_pins=roots[3],memory=Memory())


def test_same_size_restored_mtime_content_change_refuses_final_rehash(tmp_path):
    root=tmp_path/"held";root.mkdir(mode=0o700);p=root/"control.json";_put(root,p.name,b"aaaa")
    held=m._Hold(root)
    try:
        held.read(p.name,cap=4);info=p.stat()
        p.write_bytes(b"bbbb");os.utime(p,ns=(info.st_atime_ns,info.st_mtime_ns))
        with pytest.raises(m.ProviderControlsError,match="custody_refused"):held.check()
    finally:held.close()


def test_cleanup_exhausts_both_holders_and_preserves_primary_refusal():
    events=[]
    class Broken:
        def close(self):events.append("recent");raise OSError("invented close failure")
    class Warm:
        def close(self):events.append("warm")
    with pytest.raises(m.ProviderControlsError,match="cleanup_refused"):m._close_holds(Broken(),Warm())
    assert events==["recent","warm"]
    events.clear()
    with pytest.raises(m.ProviderControlsError,match="body_refused"):
        try:raise m.ProviderControlsError("body_refused")
        finally:m._close_holds(Broken(),Warm())
    assert events==["recent","warm"]


def test_metadata_actual_finally_routes_failed_recent_close_to_warm_close(roots,monkeypatch):
    original=m._Hold.close;events=[];holders=[]
    def close(self):
        holders.append(self);events.append(self.root)
        original(self)
        if self.root==roots[1]:raise OSError("invented recent cleanup failure")
    monkeypatch.setattr(m._Hold,"close",close)
    try:
        with pytest.raises(m.ProviderControlsError,match="cleanup_refused"):_metadata(roots)
        assert events[:2]==[roots[1],roots[0]]
    finally:
        for holder in holders:original(holder)


@pytest.mark.parametrize("kind",["symlink","hardlink","public_mode","fifo","ancestor"])
def test_held_private_custody_refuses_dangerous_shapes(tmp_path,kind):
    root=tmp_path/"held";root.mkdir(mode=0o700);p=root/"control.json";_put(root,p.name,b"{}")
    if kind=="symlink":p.unlink();p.symlink_to(tmp_path/"missing")
    elif kind=="hardlink":os.link(p,tmp_path/"alias")
    elif kind=="public_mode":p.chmod(0o644)
    elif kind=="fifo":p.unlink();os.mkfifo(p,0o600)
    else:root.rename(tmp_path/"real");root.symlink_to(tmp_path/"real",target_is_directory=True)
    held=None
    try:
        with pytest.raises((m.ProviderControlsError,OSError,ValueError)):
            held=m._Hold(root);held.read(p.name,cap=4)
    finally:
        if held is not None:held.close()


def test_selected_body_change_is_not_hidden_by_unchanged_metadata(roots):
    value=_metadata(roots);p=Path(value["selected"][8]["body_path"]);raw=p.read_bytes()
    p.write_bytes(raw.replace(b"INVENTED-PRIVATE",b"ALTERED--PRIVATE"))
    with pytest.raises(m.ProviderControlsError,match="external_pin_refused"):
        m.derive_invented(value,warm_pins=roots[2],recent_pins=roots[3],memory=Memory())


def test_body_phase_does_not_open_unselected_recent_parents(roots,monkeypatch):
    value=_metadata(roots);allowed={Path(v["body_path"]).name for v in value["selected"][8:]}
    original=m._Hold.read
    def read(self,relative,**kwargs):
        if self.root==roots[1] and relative.startswith("objects/"):assert relative.split("/")[1] in allowed
        return original(self,relative,**kwargs)
    monkeypatch.setattr(m._Hold,"read",read)
    result=m.derive_invented(value,warm_pins=roots[2],recent_pins=roots[3],memory=Memory())
    assert len(result["cases"])==12


def test_body_phase_rechecks_metadata_after_selected_body_work(roots,monkeypatch):
    value=_metadata(roots);original=m._case;calls=[]
    def case(*args):
        result=original(*args);calls.append(1)
        if len(calls)==12:
            p=roots[0]/"plan.json";p.write_bytes(p.read_bytes()+b" ")
        return result
    monkeypatch.setattr(m,"_case",case)
    with pytest.raises(m.ProviderControlsError):
        m.derive_invented(value,warm_pins=roots[2],recent_pins=roots[3],memory=Memory())
    assert len(calls)==12


@pytest.mark.parametrize("xml,expected",[(b"<ownershipDocument><issuer/></ownershipDocument>",None),
    (b"<ownershipDocument><issuer><issuerTradingSymbol>ZZZ.A</issuerTradingSymbol></issuer></ownershipDocument>","ZZZ.A"),
    (b'<n:ownershipDocument xmlns:n="urn:invented"><n:issuer><n:issuerTradingSymbol>ZZZ</n:issuerTradingSymbol></n:issuer></n:ownershipDocument>',"ZZZ")])
def test_symbol_is_optional_bounded_namespace_aware_source_text(xml,expected):assert m._symbol(xml)==expected


@pytest.mark.parametrize("xml",[b"<!DOCTYPE a><ownershipDocument><issuer/></ownershipDocument>",
    b"<ownershipDocument><issuer><issuerTradingSymbol>A</issuerTradingSymbol><issuerTradingSymbol>B</issuerTradingSymbol></issuer></ownershipDocument>",
    b"<ownershipDocument><issuer><issuerTradingSymbol><nested/></issuerTradingSymbol></issuer></ownershipDocument>",
    b"<ownershipDocument><issuer/><other><issuerTradingSymbol>A</issuerTradingSymbol></other></ownershipDocument>",
    b"<ownershipDocument><issuer><issuerTradingSymbol>https://evil.invalid/key</issuerTradingSymbol></issuer></ownershipDocument>"])
def test_symbol_refusals(xml):
    with pytest.raises(m.ProviderControlsError,match="symbol_refused"):m._symbol(xml)


def test_actual_fence_precedes_every_private_read(monkeypatch):
    monkeypatch.setattr(m,"_Hold",lambda *a:pytest.fail("private read before real guard"))
    with pytest.raises(m.ProviderControlsError,match="native_refused"):m.metadata_actual(memory=Memory())
    with pytest.raises(m.ProviderControlsError,match="native_refused"):m.derive_actual({},memory=Memory())


@pytest.mark.parametrize("path",[m.LANE_ROOT,m.WARM_ROOT,m.RECENT_ROOT,Path("/Volumes/SANDISK/firstrate")])
def test_fixture_fence_refuses_actual_inputs_before_reader(path,monkeypatch,tmp_path):
    monkeypatch.setattr(m,"_metadata",lambda *a,**kw:pytest.fail("actual input reached"))
    with pytest.raises(m.ProviderControlsError,match="fixture_root_refused"):
        m.metadata_invented(path,tmp_path,warm_pins={},recent_pins={},memory=Memory())


def test_fixed_initial_allowlist_and_explicit_resource_contract():
    paths=m.metadata_paths()
    assert len(paths)==len(set(paths))==16 and all(not str(p).endswith(".bin") for p in paths)
    assert m.MAX_METADATA==128*1024 and m.MAX_BODY==8*1024*1024 and m.WORKER_SECONDS==120
    assert m.RECENT_POSITIONS==(0,5,8,14)


def test_public_summary_refuses_unexpected_private_key(roots):
    value=_metadata(roots);result=m.derive_invented(value,warm_pins=roots[2],recent_pins=roots[3],memory=Memory())
    result["private_extra"]="NEVER_PRINT"
    with pytest.raises(m.ProviderControlsError):m.public_summary(result)
