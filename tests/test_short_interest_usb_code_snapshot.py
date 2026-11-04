"""Five-file RAM profile, fabricated Git/USB only; no actual archive access."""
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from types import ModuleType, SimpleNamespace

import pytest


REPOSITORY = Path(__file__).resolve().parents[1]
DRIVER = "scripts/inspect_short_interest_usb_code_snapshot.py"
HEAD, REMOTE = "a" * 40, "b" * 40


def digest(raw): return hashlib.sha256(raw).hexdigest()


def replace_assignments(raw, replacements):
    tree = ast.parse(raw)
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in replacements: node.value = ast.parse(replacements[name], mode="eval").body
    return (ast.unparse(ast.fix_missing_locations(tree)) + "\n").encode()


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    """Reviewed class bodies execute unchanged; only literal fixture policies vary.

    A toy committed MODEL has an explicit pre-registered test hook. It contains
    no market row and permits deterministic adversarial metadata timing. Git
    replies and mounted USB ancestry are ordinary temporary test boundaries.
    """
    root = (tmp_path / "lane").resolve(); usb = (tmp_path / "usb").resolve()
    root.mkdir(); usb.mkdir(); monkeypatch.chdir(root)
    # NAMED fabricated shared-host ancestry: concurrent agents may create
    # unrelated pytest directories. Freeze only ancestors ABOVE this fixture;
    # every owned code/USB file and directory retains real mutable full10.
    actual_fstat, actual_stat, actual_lstat = os.fstat, os.stat, os.lstat
    shared = {}
    for parent in tmp_path.parents:
        info=actual_lstat(parent);shared[(info.st_dev,info.st_ino)]=info
    def common(info):return shared.get((info.st_dev,info.st_ino),info)
    monkeypatch.setattr(os,"fstat",lambda fd:common(actual_fstat(fd)))
    monkeypatch.setattr(os,"stat",lambda path,*a,**kw:common(actual_stat(path,*a,**kw)))
    monkeypatch.setattr(os,"lstat",lambda path,*a,**kw:common(actual_lstat(path,*a,**kw)))
    contents = {"full": b"fabricated-full", "year": b"fabricated-year", "manifest": b"{}", "readme": b"fabricated-readme"}
    inputs = tuple((role, role + ".literal", len(raw), digest(raw)) for role, raw in contents.items())
    for role, rel, unused, unused2 in inputs: (usb / rel).write_bytes(contents[role])
    source = (REPOSITORY / DRIVER).read_bytes()
    modified = replace_assignments(source, {"ROOT": "Path(" + repr(str(root)) + ")", "USB": "Path(" + repr(str(usb)) + ")",
        "INPUTS": repr(inputs), "PROFILE_SHA256": repr("PENDING")})
    module_name = "_test_usb_window_original"
    temporary = ModuleType(module_name); temporary.__file__ = str(root / DRIVER)
    sys.modules[module_name] = temporary; exec(compile(modified, temporary.__file__, "exec"), temporary.__dict__)
    modified = replace_assignments(modified, {"PROFILE_SHA256": repr(temporary._hash(temporary.policy()))})
    module = ModuleType(module_name); module.__file__ = str(root / DRIVER)
    sys.modules[module_name] = module; exec(compile(modified, module.__file__, "exec"), module.__dict__)
    old_reader = replace_assignments((REPOSITORY / module.READER).read_bytes(), {"INPUTS": repr(inputs)})
    model = b'''from dataclasses import dataclass
from data.hashing import hash_payload
import sys
_ISSUED = {}
def inspection_policy(): return {"fixture":True,"source_admitted":False}
@dataclass(frozen=True,slots=True)
class Report:
    hashes: str
    def to_payload(self): return {"fixture":True,"source_admitted":False,"inputs_sha256":self.hashes}
def inspect_registered_pair(**blobs):
    sys._si_usb_fixture_hook("model")
    assert tuple(blobs)==("full","year","manifest","readme")
    value=Report(hash_payload({key:list(raw) for key,raw in blobs.items()}))
    _ISSUED[id(value)] = value
    return value
'''
    committed = {"data/__init__.py": b"", "data/hashing.py": (REPOSITORY / "data/hashing.py").read_bytes(),
        module.MODEL: model, module.READER: old_reader, DRIVER: modified}
    for name, raw in committed.items():
        path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
    h = SimpleNamespace(module=module, root=root, usb=usb, committed=committed, tick=10., calls=[], shows=0,
        action=None, on_git=None, model_seen=False)
    def hook(stage):
        assert stage == "model"; h.model_seen = True
        if h.action is not None: h.action(h)
    monkeypatch.setattr(sys, "_si_usb_fixture_hook", hook, raising=False)
    monkeypatch.setattr(module.time, "monotonic", lambda: h.tick)
    def git(arguments, **kwargs):
        assert arguments[0] == "git" and kwargs["cwd"] == root
        assert kwargs["stdin"] is None and kwargs["env"] == {"PATH": "/usr/bin:/bin", "GIT_OPTIONAL_LOCKS": "0"}
        args = tuple(arguments[1:]); h.calls.append(args)
        replies = {("rev-parse", "--show-toplevel"): str(root).encode(), ("branch", "--show-current"): b"codex/strategy-short-interest",
            ("rev-parse", "HEAD"): HEAD.encode(), ("status", "--porcelain=v1", "-z", "--untracked-files=all"): b"",
            ("rev-parse", "refs/remotes/origin/codex/strategy-short-interest"): REMOTE.encode(),
            ("ls-remote", "--exit-code", "--refs", "origin", "refs/heads/codex/strategy-short-interest"): (REMOTE + "\trefs/heads/codex/strategy-short-interest").encode()}
        if args[0] == "show":
            head, name = args[1].split(":", 1); assert head == HEAD and name in committed
            h.shows += 1
            if h.on_git is not None: h.on_git(h, name)
            raw = committed[name]
        else:
            assert args in replies
            raw = replies[args]
            if h.on_git is not None: h.on_git(h, args[0])
        return SimpleNamespace(returncode=0, stdout=raw, stderr=b"")
    monkeypatch.setattr(subprocess, "run", git)
    try: yield h
    finally:
        for name in module._ALIASES:
            sys.modules.pop(name, None)
        sys.modules.pop(module_name, None)


def run(h): return h.module.inspect_registered(HEAD, REMOTE)


def negative(h):
    with pytest.raises(h.module.CodeSnapshotRefusal) as caught: run(h)
    return h.module.failure_summary(caught.value)


def test_original_whole_five_file_profile_and_closed_observation(fixture):
    h = fixture; result = run(h)
    assert h.model_seen and result["status"] == "closed_finite_code_windows_external_byte_inspection"
    assert result["code_file_original10_equal"] is result["executed_verified_RAM"] is True
    assert result["all_initial_code_contexts_closed"] is result["all_source_contexts_closed"] is result["all_terminal_code_contexts_closed"] is True
    assert result["continuous_shared_ancestor_timestamp_custody"] is False
    assert result["initial_code_file10_sha256"] == result["terminal_code_file10_sha256"]
    assert len(h.module.CODE_FILES) == 5 and not any(name in sys.modules for name in h.module._ALIASES)
    assert all(value is False or type(value) is int and value == 0 for key,value in result["authority"].items() if key != "external_byte_inspection_only")
    snapshot = next(iter(h.module._SNAPSHOTS.values()))[0]
    with pytest.raises(h.module.CodeSnapshotRefusal, match="snapshot_failed"): snapshot._record()


def test_old_reader_and_pure_model_production_files_are_not_runtime_imported(fixture,monkeypatch):
    h = fixture
    existing={name:module for name,module in tuple(sys.modules.items()) if name.startswith("research.short_interest_etf.firstrate")}
    import data.hashing as live
    monkeypatch.setattr(live,"hash_payload",lambda *args:pytest.fail("live hashing module was used"))
    for module in existing.values():
        if hasattr(module,"inspect_registered_pair"):
            monkeypatch.setattr(module,"inspect_registered_pair",lambda *args,**kwargs:pytest.fail("live model module was used"))
    assert run(h)["executed_verified_RAM"] is True
    after={name:module for name,module in tuple(sys.modules.items()) if name.startswith("research.short_interest_etf.firstrate")}
    assert set(after)==set(existing) and all(after[name] is module for name,module in existing.items())


def test_gap_only_shared_code_ancestor_drift_is_explicitly_limited_not_rebaselined(fixture):
    h = fixture
    def action(h):
        path = h.root / "data"; info = path.stat()
        os.utime(path, ns=(info.st_atime_ns,info.st_mtime_ns+1000000))
    h.action = action; result = run(h)
    assert result["continuous_shared_ancestor_timestamp_custody"] is False
    assert result["initial_ancestor_observations_sha256"] != result["terminal_ancestor_observations_sha256"]
    assert result["initial_code_file10_sha256"] == result["terminal_code_file10_sha256"]


@pytest.mark.parametrize("window",["initial","terminal"])
def test_same_ancestor_drift_inside_each_window_refuses(fixture,window):
    h = fixture
    def mutate(h,name):
        if h.shows == (6 if window=="initial" else 11) and name == h.module.CODE_FILES[0]:
            path=h.root/"data"; info=path.stat(); os.utime(path,ns=(info.st_atime_ns,info.st_mtime_ns+1000000))
    h.on_git=mutate; report=negative(h)
    assert h.model_seen is (window=="terminal") and report["first_failure"]["phase"] == window+"_code"
    assert report["first_failure"]["original_comparison"] is not None
    if window=="initial":assert not h.module._SNAPSHOTS


@pytest.mark.parametrize("change", ["bytes", "mtime", "replace"])
def test_gap_code_file_change_never_becomes_a_new_original(fixture,change):
    h=fixture
    def action(h):
        path=h.root/"data/hashing.py"
        if change=="bytes": path.write_bytes(path.read_bytes()+b"\n")
        elif change=="mtime":
            info=path.stat();os.utime(path,ns=(info.st_atime_ns,info.st_mtime_ns+1000000))
        else:
            raw=path.read_bytes();path.unlink();path.write_bytes(raw)
    h.action=action;report=negative(h)
    assert h.model_seen and report["first_failure"]["phase"] == "terminal_code"
    assert report["first_failure"]["code"] == "code_changed"


@pytest.mark.parametrize("change", ["global", "function", "method", "code_identity", "resolver", "alias"])
def test_snapshot_module_global_callable_import_or_class_substitution_refuses(fixture,change):
    h=fixture
    def action(h):
        graph=next(iter(h.module._SNAPSHOTS.values()))[1]
        if change=="global": graph.reader.INPUTS=()
        elif change=="function": graph.hashing.hash_payload=lambda *args: "a"*64
        elif change=="method": graph.reader._Read.audit=lambda self: None
        elif change=="code_identity": graph.reader._Read.audit.__code__=graph.reader._Read.audit.__code__.replace()
        elif change=="resolver": graph.import_table["data.hashing"]=ModuleType("untrusted")
        else: sys.modules[h.module._ALIASES[2]]=ModuleType("untrusted")
    h.action=action;report=negative(h)
    assert report["first_failure"]["phase"] == "model"
    assert report["first_failure"]["code"] in ("graph_changed","import_refused","namespace_changed")


@pytest.mark.parametrize("change", ["bytes", "mtime", "replace", "parent"])
def test_USB_data_checks_remain_continuous_and_strict(fixture,change):
    h=fixture
    def action(h):
        path=h.usb/"full.literal"
        if change=="bytes": path.write_bytes(b"CHANGED")
        elif change=="replace":
            raw=path.read_bytes();path.unlink();path.write_bytes(raw)
        else:
            path=h.usb if change=="parent" else path
            info=path.stat();os.utime(path,ns=(info.st_atime_ns,info.st_mtime_ns+1000000))
    h.action=action;report=negative(h)
    assert report["first_failure"]["phase"] in ("source_audit","model")
    assert report["first_failure"]["original_comparison"] is not None


def test_whole_deadline_after_model_cannot_reset_or_return_provisional(fixture):
    h=fixture;h.action=lambda h:setattr(h,"tick",h.tick+181)
    report=negative(h)
    assert report["first_failure"]["code"] == "clock_failed"
    assert report["cleanup_failures"]


def test_first_model_failure_survives_later_namespace_cleanup_failure(fixture):
    h=fixture
    def action(h):
        sys.modules[h.module._ALIASES[0]]=ModuleType("replacement")
        raise RuntimeError("PRIVATE fabricated error /secret/path")
    h.action=action;report=negative(h)
    assert report["first_failure"]["phase"] == "model" and report["first_failure"]["code"] is None
    assert any(row["code"] == "namespace_changed" for row in report["cleanup_failures"])
    assert "PRIVATE" not in json.dumps(report) and "/secret/path" not in json.dumps(report)


def test_copied_snapshot_with_original_frame_is_not_a_factory_capability(fixture):
    h=fixture
    def action(h):
        original=next(iter(h.module._SNAPSHOTS.values()))[0]
        forged=object.__new__(h.module.CodeSnapshot);row=(forged,*original._anchor[1:])
        forged._anchor=row;h.module._SNAPSHOTS[id(forged)]=row
        with pytest.raises(h.module.CodeSnapshotRefusal,match="snapshot_factory"):forged._record()
        assert original._record()[0] is original
        with pytest.raises(h.module.CodeSnapshotRefusal,match="snapshot_factory"):
            h.module._issue_snapshot(original._anchor[1],original._anchor[2],original._anchor[3],original._anchor[5],original._anchor[6])
    h.action=action;assert run(h)["executed_verified_RAM"] is True


def test_preoccupied_private_namespace_refuses_before_initial_or_source_context(fixture):
    h=fixture;sentinel=ModuleType("prior");sys.modules[h.module._ALIASES[0]]=sentinel
    report=negative(h)
    assert report["first_failure"]["code"] == "namespace_occupied"
    assert sys.modules[h.module._ALIASES[0]] is sentinel and not h.model_seen


def test_code_snapshot_constructor_and_unknown_refusal_never_accept_caller_flags(fixture):
    h=fixture
    with pytest.raises(h.module.CodeSnapshotRefusal,match="snapshot_factory"):h.module.CodeSnapshot()
    error=h.module.CodeSnapshotRefusal({"PRIVATE":"/secret"})
    report=h.module.failure_summary(error)
    assert report["first_failure"]["code"] is None and "PRIVATE" not in json.dumps(report)


def test_production_profile_registration_five_code_catalogue_and_unchanged_old_sources():
    source=(REPOSITORY/DRIVER).read_bytes();compile(source,str(REPOSITORY/DRIVER),'exec')
    module=ModuleType("_usb5_policy_only");module.__file__=str(REPOSITORY/DRIVER)
    exec(compile(source,module.__file__,'exec'),module.__dict__)
    module._registered()
    assert module.CODE_FILES==("data/__init__.py","data/hashing.py",module.MODEL,module.READER,DRIVER)
    assert module.MAX_SECONDS==180


@pytest.mark.parametrize("field", ("dev","ino","uid","gid","mode","nlink","size","mtime_ns","ctime_ns","flags"))
def test_every_original_USB_stamp_field_still_refuses_without_rebaseline(fixture,monkeypatch,field):
    h=fixture; actual=os.fstat; target=(h.usb/"full.literal").stat()
    def overlay(fd):
        info=actual(fd)
        if h.model_seen and (info.st_dev,info.st_ino)==(target.st_dev,target.st_ino):
            values={key:getattr(info,key) for key in dir(info) if key.startswith("st_")}
            name="st_"+field;values[name]=values.get(name,0)+1
            return SimpleNamespace(**values)
        return info
    monkeypatch.setattr(os,"fstat",overlay)
    report=negative(h);detail=report["first_failure"]["original_comparison"]
    assert detail is not None and detail["mismatching_fields"]==[field]
    assert detail["relation"]=="file_descriptor_before_bytes_vs_original"


def test_USB_metadata_change_after_LAST_fresh_close_is_still_refused(fixture,monkeypatch):
    h=fixture; actual=os.close; target=h.usb/"full.literal"; inode=target.stat().st_ino; closes=0
    def close(fd):
        nonlocal closes
        selected=os.fstat(fd).st_ino==inode
        actual(fd)
        if selected and h.model_seen:
            closes+=1
            if closes==2:
                info=target.stat();os.utime(target,ns=(info.st_atime_ns,info.st_mtime_ns+1000000))
    monkeypatch.setattr(os,"close",close)
    report=negative(h)
    assert report["first_failure"]["phase"]=="source_after_close"
    assert report["first_failure"]["original_comparison"]["entered_phase"]=="post_close_named_audit"


def test_terminal_code_metadata_change_after_LAST_fresh_close_is_refused(fixture,monkeypatch):
    h=fixture;actual=os.close;target=h.root/"data/hashing.py";inode=target.stat().st_ino;closes=0
    def close(fd):
        nonlocal closes
        selected=os.fstat(fd).st_ino==inode;actual(fd)
        if selected:
            closes+=1
            if closes==4:
                info=target.stat();os.utime(target,ns=(info.st_atime_ns,info.st_mtime_ns+1000000))
    monkeypatch.setattr(os,"close",close)
    report=negative(h)
    assert report["first_failure"]["phase"]=="terminal_code"
    assert report["first_failure"]["original_comparison"]["entered_phase"]=="post_close_named_audit"


@pytest.mark.parametrize("window",["initial","terminal"])
def test_original_code_context_close_failure_prevents_positive(fixture,monkeypatch,window):
    h=fixture; actual=os.close; inode=(h.root/"data/__init__.py").stat().st_ino;closes=0
    def close(fd):
        nonlocal closes
        selected=os.fstat(fd).st_ino==inode;actual(fd)
        if selected:
            closes+=1
            if closes==(1 if window=="initial" else 3): raise OSError("PRIVATE fabricated close error")
    monkeypatch.setattr(os,"close",close)
    report=negative(h)
    assert report["first_failure"]["phase"]==window+"_code"
    assert report["first_failure"]["code"]=="descriptor_close_failed"
    assert h.model_seen is (window=="terminal") and "PRIVATE" not in json.dumps(report)


def test_source_constructor_comparison_survives_its_own_cleanup_failure(fixture,monkeypatch):
    h=fixture; target=h.usb/"full.literal"; original_read=os.read;original_close=os.close; altered=False
    inode=target.stat().st_ino;failed=False
    def read(fd,size):
        nonlocal altered
        raw=original_read(fd,size)
        if not altered and os.fstat(fd).st_ino==inode:
            altered=True;info=target.stat();os.utime(target,ns=(info.st_atime_ns,info.st_mtime_ns+1000000))
        return raw
    def close(fd):
        nonlocal failed
        selected=os.fstat(fd).st_ino==inode;original_close(fd)
        if selected and not failed: failed=True;raise OSError("PRIVATE cleanup override")
    monkeypatch.setattr(os,"read",read);monkeypatch.setattr(os,"close",close)
    report=negative(h)
    assert report["first_failure"]["code"]=="descriptor_close_failed"
    contexts=[fact for fact in report["cleanup_failures"] if fact.get("exception_context_observation")]
    assert any(fact["original_comparison"] is not None and "mtime_ns" in fact["original_comparison"]["mismatching_fields"] for fact in contexts)
    assert all(fact["phase"]=="unknown" and fact["role"]=="unknown" for fact in contexts)
    assert not h.model_seen and "PRIVATE" not in json.dumps(report)


def test_unknown_inner_primary_and_genuine_cleanup_remain_separate_context_observations(fixture):
    h=fixture
    def action(h):
        graph=next(iter(h.module._SNAPSHOTS.values()))[1]
        original=next(row[0] for row in graph.reader._READ_ORIGINS.values() if row[0].path==h.usb/"full.literal")
        try:raise RuntimeError("PRIVATE unknown earlier failure")
        except RuntimeError:
            info=original.path.stat();os.utime(original.path,ns=(info.st_atime_ns,info.st_mtime_ns+1000000))
            original.audit() # Genuine comparison, later than the unknown context.
    h.action=action;report=negative(h)
    assert report["failure_ordering"]=="first_caught_at_owned_boundary_contexts_are_observations"
    assert report["first_failure"]["phase"]=="model" and report["first_failure"]["original_comparison"] is not None
    contexts=[fact for fact in report["cleanup_failures"] if fact.get("exception_context_observation")]
    assert any(fact["code"] is None and fact["original_comparison"] is None for fact in contexts)
    assert all(fact["phase"]=="unknown" and fact["role"]=="unknown" for fact in contexts)
    assert "PRIVATE" not in json.dumps(report)


@pytest.mark.parametrize("kind",["HEAD","remote"])
def test_terminal_lane_or_remote_change_prevents_observation(fixture,monkeypatch,kind):
    h=fixture; original=subprocess.run
    def git(args,**kwargs):
        result=original(args,**kwargs)
        selected=tuple(args[1:])==(("rev-parse","HEAD") if kind=="HEAD" else ("ls-remote","--exit-code","--refs","origin","refs/heads/codex/strategy-short-interest"))
        if h.model_seen and selected: result.stdout=("c"*40).encode()
        return result
    monkeypatch.setattr(subprocess,"run",git)
    report=negative(h)
    assert report["first_failure"]["code"]==("lane_changed" if kind=="HEAD" else "remote_changed")


def test_snapshot_runtime_function_substitution_is_permanently_vetoed(fixture):
    h=fixture
    def action(h):
        h.module._sha=lambda raw:"a"*64
    h.action=action
    # The retained original runtime verifier catches the substituted helper;
    # failure formatting itself need not invoke that substituted helper.
    report=negative(h)
    assert report["first_failure"]["code"]=="runtime_changed"


def test_original_bootstrap_module_binding_cannot_be_replaced_midrun(fixture):
    h=fixture
    def action(h):sys.modules[h.module.__name__]=ModuleType("replacement_bootstrap")
    h.action=action;report=negative(h)
    assert report["first_failure"]["code"]=="namespace_changed"


def test_hash_primitive_cannot_be_substituted_midrun(fixture,monkeypatch):
    h=fixture
    def action(h):
        monkeypatch.setattr(hashlib,"sha256",lambda raw:SimpleNamespace(hexdigest=lambda:"a"*64))
    h.action=action;report=negative(h)
    assert report["first_failure"]["code"]=="runtime_changed"


def test_final_format_clock_includes_namespace_cleanup_and_last_serialization(fixture,monkeypatch):
    h=fixture; original=json.dumps
    def dumps(value,*args,**kwargs):
        raw=original(value,*args,**kwargs)
        if isinstance(value,dict) and "observation_sha256" in value:h.tick+=181
        return raw
    monkeypatch.setattr(json,"dumps",dumps)
    report=negative(h)
    assert report["first_failure"]["phase"]=="final_format" and report["first_failure"]["code"]=="clock_failed"


def test_git_subprocess_metadata_has_no_Python_write_open_under_unchanged_denial():
    code=r'''
import sys,os,importlib.util
sys.dont_write_bytecode=True
path=sys.argv[1];spec=importlib.util.spec_from_file_location("_usb5_Git_only",path)
module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
attempts=[]
def audit(event,args):
 if event=="open" and args[2]&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND):
  attempts.append(True);raise RuntimeError("write_open_denied")
sys.addaudithook(audit)
clock=module._Clock()
assert module._git(clock,"rev-parse","--show-toplevel").decode().strip()==str(module.ROOT)
assert attempts==[]
print("Git_no_write_open")
'''
    result=subprocess.run([sys.executable,"-I","-S","-B","-c",code,str(REPOSITORY/DRIVER)],cwd=REPOSITORY,
        env={"PATH":"/usr/bin:/bin"},stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
    assert result.returncode==0,result.stderr.decode()
    assert result.stdout.strip()==b"Git_no_write_open"
