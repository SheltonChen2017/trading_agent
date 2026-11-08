"""Invented data-only epochs; no actual root, source, credential or provider IO."""
from copy import deepcopy
import hashlib
import os
from pathlib import Path
import stat
import sys
import shutil
from types import SimpleNamespace

import pytest

pytest.importorskip("fcntl", reason="qualified macOS/POSIX private custody stack")
from research import insider_buying_pilot_stable_custody_v2 as m


@pytest.fixture
def storage(tmp_path):
    root = tmp_path / "invented-private-custody"; root.mkdir(mode=0o700)
    return root


@pytest.fixture
def memory():
    if sys.platform != "darwin": pytest.skip("real Darwin VM/RSS guard required")
    guard = m.native._WorkerMemoryGuard()
    try: yield guard
    finally: guard.close()


def _epoch(storage, **kwargs):
    return m.Epoch({"head": "1" * 40}, {"audit_id": "invented-one", "nested": {"value": 3}},
        fixture=True, fixture_root=storage, checker=lambda: None, **kwargs)


def _write(root, name, value):
    p = root / name; p.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    raw = m._raw(value)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream: stream.write(raw)
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def _old_root(storage):
    root = storage / "old-failed-epoch"; root.mkdir(mode=0o700)
    for directory in (m.LEGACY_AUDIT, m.LEGACY_SECOND, m.LEGACY_THIRD): (root/directory).mkdir(mode=0o700)
    pins = {}
    for name, head in zip(list(m.SNAPSHOT_PINS)[:3], m.LEGACY_HEADS):
        pins[name] = _write(root, name, {"fixture_only": True, "execution_identity": {"head": head}})
    for name in m.SNAPSHOT_PINS:
        if "/" in name: pins[name] = _write(root, name, {"invented_control": True})
    return root, pins


def test_epoch_has_separate_storage_and_unchanged_repository_identity(storage):
    identity = {"head": "1"*40}; registration = {"audit_id": "invented-one", "nested": {"v": [1]}}
    e = m.Epoch(identity, registration, fixture=True, fixture_root=storage, checker=lambda: None)
    try:
        identity["head"] = "secret"; registration["nested"]["v"].append(2)
        assert e.root == m.LANE_ROOT and e.storage_root == storage and e.fixture is True
        assert e.is_actual() is False and set(e.pins) == {"reservation.json"}
        assert e.latch == e.pins["reservation.json"]
        assert e.read("reservation.json")["registration"]["nested"] == {"v": [1]}
        first = e.publish("controls.json", {"rows": 12})
        assert first == e.pins["controls.json"]["sha256"] and e.read("controls.json") == {"rows": 12}
        mutable = e.pins; mutable["controls.json"]["sha256"] = "0"*64
        e.check()
    finally: e.close()


def test_claim_is_exclusive_and_never_resumes(storage):
    e = _epoch(storage); original = (storage/"invented-one"/"reservation.json").read_bytes(); e.close()
    with pytest.raises(m.CustodyError, match="namespace_consumed"): _epoch(storage)
    assert (storage/"invented-one"/"reservation.json").read_bytes() == original


@pytest.mark.parametrize("field,value", (("fixture",False),("root",Path("/invented")),("storage_root",Path("/invented")),("audit_id","other")))
def test_public_context_mutation_never_promotes_fixture(storage, field, value):
    e = _epoch(storage)
    try:
        setattr(e, field, value)
        assert e.is_actual() is False
        with pytest.raises(m.CustodyError, match="identity_refused"): e.check()
    finally: e.close()


@pytest.mark.parametrize("which", ("identity", "registration"))
def test_mutated_owned_payload_refuses_before_new_file(storage, which):
    e = _epoch(storage)
    try:
        getattr(e, which)["extra"] = "invented"
        with pytest.raises(m.CustodyError): e.publish("new.json", {})
        assert not (storage/"invented-one"/"new.json").exists()
    finally: e.close()


@pytest.mark.parametrize("name", ("../escape", "UPPER.json", "x/y.json", "", [], "a"*101))
def test_bad_leaf_name_refuses_before_creation(storage, name):
    e = _epoch(storage)
    try:
        with pytest.raises(m.CustodyError): e.publish(name, {})
        assert set(os.listdir(e.directory.fd)) == {"reservation.json"}
    finally: e.close()


def test_duplicate_publication_preserves_first_bytes(storage):
    e = _epoch(storage)
    try:
        e.publish("controls.json", {"first": True}); raw=(storage/"invented-one"/"controls.json").read_bytes()
        with pytest.raises(m.CustodyError, match="namespace_consumed"): e.publish("controls.json", {"first": False})
        assert (storage/"invented-one"/"controls.json").read_bytes() == raw
    finally: e.close()


def test_same_size_mtime_restored_content_change_is_caught(storage, monkeypatch):
    e = _epoch(storage)
    try:
        e.publish("controls.json", {"v": 1}); p=storage/"invented-one"/"controls.json"; original=p.stat()
        p.write_bytes(b'{"v":2}'); os.utime(p,ns=(original.st_atime_ns,original.st_mtime_ns))
        # Remove the independent ctime direction to reach the content check.
        e._pins["controls.json"]["version"] = m.custody._version(p.stat())
        with pytest.raises(m.CustodyError) as caught: e.check()
        assert caught.value.changed_fields == ("content",)
    finally: e.close()


@pytest.mark.parametrize("fault", ("mode", "link", "replace", "symlink"))
def test_privacy_and_identity_failure_never_reads_or_hashes_foreign_bytes(storage, monkeypatch, fault):
    e = _epoch(storage)
    try:
        e.publish("controls.json", {"private": 1}); p=storage/"invented-one"/"controls.json"
        if fault=="mode": p.chmod(0o644)
        elif fault=="link": os.link(p,storage/"other-link")
        elif fault=="replace":
            p.unlink(); _write(storage/"invented-one","controls.json",{"private":1})
        else:
            p.unlink(); p.symlink_to(storage/"unopened-credential")
        original=m.os.pread
        def no_foreign(fd,*args):
            if os.fstat(fd).st_ino == p.lstat().st_ino: pytest.fail("read invalid/replaced leaf")
            return original(fd,*args)
        monkeypatch.setattr(m.os,"pread",no_foreign)
        with pytest.raises(m.CustodyError): e.check()
    finally: e.close()


def test_ctime_only_postseal_change_reports_role_and_field_without_values(storage, monkeypatch):
    e = _epoch(storage)
    try:
        e.publish("controls.json", {"v":1}); p=storage/"invented-one"/"controls.json"
        e._pins["controls.json"]["version"] = (*e._pins["controls.json"]["version"][:-1],0)
        monkeypatch.setattr(m.os,"pread",lambda *_: pytest.fail("ctime failure must precede bytes"))
        with pytest.raises(m.CustodyError) as caught: m._read_leaf(e.directory.fd,"controls.json",e._pins["controls.json"])
        assert m.safe_failure(caught.value)=={"code":"output_changed","role":"controls","changed_fields":["ctime"]}
        assert str(p) not in str(caught.value)
    finally: e.close()


def test_external_size_mismatch_refuses_before_read_or_hash(storage,monkeypatch):
    pin=_write(storage,"owned.json",{"own":True});pin["bytes"]+=1
    fd=os.open(storage,os.O_RDONLY|os.O_DIRECTORY)
    monkeypatch.setattr(m.os,"pread",lambda *_:pytest.fail("read before external size binding"))
    try:
        with pytest.raises(m.CustodyError) as caught:m._read_leaf(fd,"owned.json",pin)
        assert caught.value.changed_fields==("size",)
    finally:os.close(fd)


@pytest.mark.parametrize("fault",("mode","link"))
def test_external_pin_privacy_refusal_precedes_any_data_read(storage,monkeypatch,fault):
    pin=_write(storage,"owned.json",{"own":True});p=storage/"owned.json"
    if fault=="mode":p.chmod(0o644)
    else:os.link(p,storage/"second-name")
    fd=os.open(storage,os.O_RDONLY|os.O_DIRECTORY)
    monkeypatch.setattr(m.os,"pread",lambda *_:pytest.fail("read privacy-invalid external leaf"))
    try:
        with pytest.raises(m.CustodyError):m._read_leaf(fd,"owned.json",pin)
    finally:os.close(fd)


@pytest.mark.parametrize("audit_id",("../escape","/escape","UPPER","a"*97,[],True))
def test_bad_audit_namespace_refuses_before_checker_or_storage(storage,audit_id):
    with pytest.raises(m.CustodyError):
        m.Epoch({}, {"audit_id":audit_id},fixture=True,fixture_root=storage,
            checker=lambda:pytest.fail("checker before audit namespace validation"))
    assert not list(storage.iterdir())


def test_inventory_and_ancestor_replacement_refuse(storage):
    e = _epoch(storage)
    try:
        _write(storage/"invented-one","unregistered.json",{})
        with pytest.raises(m.CustodyError) as caught: e.check()
        assert caught.value.changed_fields == ("inventory",)
        (storage/"invented-one"/"unregistered.json").unlink()
        (storage/"invented-one").rename(storage/"moved")
        (storage/"invented-one").mkdir(mode=0o700)
        with pytest.raises(m.CustodyError): e.check()
    finally: e.close()


def test_close_exhausts_every_owned_fd_and_preserves_primary(storage, monkeypatch):
    fds=[os.open(storage,os.O_RDONLY|os.O_DIRECTORY) for _ in range(3)];seen=[];real=m.os.close
    chain=SimpleNamespace(fds=list(fds))
    def close(fd):
        seen.append(fd)
        if fd==fds[-1]: raise OSError("INVENTED SECRET")
        real(fd)
    monkeypatch.setattr(m.os,"close",close)
    try:
        with pytest.raises(m.CustodyError,match="cleanup_refused"): m._close_chains((chain,))
        assert seen==list(reversed(fds)) and chain.fds==[]
    finally: real(fds[-1])


def test_parent_git_check_disables_optional_locks_without_modifying_identity(storage, monkeypatch):
    from research import insider_buying_pilot_fmp_eod_qualification_v1 as legacy
    identity={"head":"1"*40};calls=[]
    monkeypatch.setattr(legacy,"_current",lambda v: calls.append(("source",deepcopy(v))))
    def git(root,*args):
        calls.append((str(root),args));return ("# branch.oid "+"1"*40+"\n# branch.head "+m.LANE_BRANCH+"\n").encode()
    monkeypatch.setattr(m.custody,"_git",git)
    m.production_parent_current(identity)
    assert calls[-1][1]==("--no-optional-locks","status","--porcelain=v2","--branch","--untracked-files=all")
    assert identity=={"head":"1"*40}


def _fake_home(storage,monkeypatch):
    home=storage/"invented-home";home.mkdir(mode=0o700)
    library=home/"Library";library.mkdir(mode=0o755)
    app=library/"Application Support";app.mkdir(mode=0o755)
    monkeypatch.setattr(m,"_HOME",home)
    monkeypatch.setattr(m,"PRIVATE_CUSTODY_ROOT",app/"trading_agent"/"insider_buying"/"custody")
    return app


def test_preparation_preserves_ancestor_modes_and_creates_only_managed_suffix(storage,monkeypatch):
    app=_fake_home(storage,monkeypatch);(app/"trading_agent").mkdir(mode=0o755)
    root=m.prepare_actual_root()
    assert root==m.PRIVATE_CUSTODY_ROOT and stat.S_IMODE(app.stat().st_mode)==0o755
    assert stat.S_IMODE((app/"trading_agent").stat().st_mode)==0o755
    assert stat.S_IMODE(root.parent.stat().st_mode)==stat.S_IMODE(root.stat().st_mode)==0o700


def test_unsafe_lane_parent_refuses_before_creating_any_descendant(storage,monkeypatch):
    app=_fake_home(storage,monkeypatch);(app/"trading_agent").mkdir(mode=0o755)
    lane=app/"trading_agent"/"insider_buying";lane.mkdir(mode=0o700);lane.chmod(0o777)
    with pytest.raises(m.CustodyError):m.prepare_actual_root()
    assert not (lane/"custody").exists() and stat.S_IMODE(lane.stat().st_mode)==0o777


def test_held_chain_constructor_cleanup_exhausts_after_close_failure(storage,monkeypatch):
    opened=[];closed=[];realopen=m.os.open;realclose=m.os.close
    def op(*args,**kwargs):
        fd=realopen(*args,**kwargs);opened.append(fd);return fd
    def cl(fd):
        closed.append(fd)
        if len(closed)==1:raise OSError("invented close failure")
        realclose(fd)
    monkeypatch.setattr(m.os,"open",op);monkeypatch.setattr(m.os,"close",cl)
    try:
        with pytest.raises(OSError):m._HeldChain(storage,("missing-component",))
        assert closed==list(reversed(opened)) and len(opened)>1
    finally:
        if closed:realclose(closed[0])


def test_native_snapshot_proves_only_failed_claim_inventory_and_detaches(storage, memory):
    root,pins=_old_root(storage);value=m.snapshot_invented(root,pins=pins,memory=memory)
    assert value["prior_provider_invocations_proved_zero"] is True
    assert value["prior_credential_reads_proved_zero"] is True and value["candidate_controls_promoted"] is False
    assert value["previous_operations_successful"] is False and len(value["pins"])==7
    assert set(value)==set(m.validate_snapshot(value,fixture=True))
    assert "invented_control" not in m._raw(value).decode()
    with pytest.raises(m.CustodyError): m.validate_snapshot(value)


@pytest.mark.parametrize("fault", ("request", "credential", "extra-root", "extra-third", "pin", "symlink", "mode"))
def test_snapshot_refuses_claim_evidence_extra_state_or_bad_bytes(storage,memory,fault):
    root,pins=_old_root(storage)
    if fault=="request": _write(root/m.LEGACY_THIRD,"request-000-started.json",{})
    elif fault=="credential": _write(root/m.LEGACY_SECOND,"fmp-credential-started.json",{})
    elif fault=="extra-root": _write(root,"extra.json",{})
    elif fault=="extra-third": _write(root/m.LEGACY_THIRD,"extra.json",{})
    elif fault=="pin": pins["scope-reservation.json"]["sha256"]="0"*64
    elif fault=="mode": (root/"scope-reservation.json").chmod(0o644)
    else:
        (root/"scope-reservation.json").unlink();(root/"scope-reservation.json").symlink_to(storage/"unopened")
    with pytest.raises(m.CustodyError):m.snapshot_invented(root,pins=pins,memory=memory)


@pytest.mark.parametrize("field", ("candidate_controls_promoted","prior_provider_invocations_proved_zero","root_entries","unknown"))
def test_snapshot_pure_validator_never_promotes_asserted_flags(storage,memory,field):
    root,pins=_old_root(storage);value=m.snapshot_invented(root,pins=pins,memory=memory)
    value[field]=True if field in {"candidate_controls_promoted","unknown"} else False
    with pytest.raises(m.CustodyError):m.validate_snapshot(value,fixture=True)


def _complete_epoch(storage):
    e=_epoch(storage);e.publish("synthetic-000.json",{"own_synthetic":True})
    published={n:{"bytes":p["bytes"],"sha256":p["sha256"]} for n,p in e.pins.items()}
    e.publish("complete.json",{"published_leaf_pins":published,"own_synthetic":True,"storage_identity":e.storage_identity})
    pins=e.pins;e.close()
    return tuple(pins),pins


def test_readback_authenticates_external_complete_before_using_derived_pins(storage,memory):
    names,pins=_complete_epoch(storage)
    result=m.read_epoch_controls_invented(storage,"invented-one",names,
        {"complete.json":{"bytes":None,"sha256":pins["complete.json"]["sha256"]}},memory=memory)
    assert set(result["controls"])==set(names) and len(result["pins"])==3
    allpins={n:{"bytes":p["bytes"],"sha256":p["sha256"]} for n,p in pins.items()}
    assert m.read_epoch_controls_invented(storage,"invented-one",names,allpins,memory=memory)==result


@pytest.mark.parametrize("fault", ("external-complete", "derived-leaf", "unlisted-leaf"))
def test_readback_refuses_self_pins_or_incomplete_inventory(storage,memory,monkeypatch,fault):
    names,pins=_complete_epoch(storage)
    external={"complete.json":{"bytes":None,"sha256":pins["complete.json"]["sha256"]}}
    if fault=="external-complete": external["complete.json"]["sha256"]="0"*64
    elif fault=="derived-leaf": (storage/"invented-one"/"synthetic-000.json").write_bytes(b'{"own_synthetic":false}')
    else:_write(storage/"invented-one","unlisted.json",{})
    if fault=="external-complete":
        source_decode=m._decode;complete_raw=(storage/"invented-one"/"complete.json").read_bytes()
        def decode(raw):
            if raw==complete_raw:pytest.fail("decode source complete before external SHA")
            return source_decode(raw)
        monkeypatch.setattr(m,"_decode",decode)
    with pytest.raises(m.CustodyError):m.read_epoch_controls_invented(storage,"invented-one",names,external,memory=memory)


def test_copied_probe_on_replaced_root_cannot_rebind_physical_storage(storage,memory):
    names,pins=_complete_epoch(storage);old=storage.with_name("retired-data-root")
    storage.rename(old);storage.mkdir(mode=0o700)
    shutil.copytree(old/"invented-one",storage/"invented-one",copy_function=shutil.copy2)
    external={"complete.json":{"bytes":None,"sha256":pins["complete.json"]["sha256"]}}
    with pytest.raises(m.CustodyError,match="identity_refused"):
        m.read_epoch_controls_invented(storage,"invented-one",names,external,memory=memory)


def test_storage_identity_is_detached_and_bound_to_held_root(storage):
    e=_epoch(storage)
    try:
        value=e.storage_identity;value["inode"]=0
        assert e.storage_identity["inode"]!=0 and e.storage_identity["mode"]==0o700
        storage.rename(storage.with_name("moved-root"));storage.mkdir(mode=0o700)
        with pytest.raises(m.CustodyError):e.check()
    finally:e.close()


def test_finite_failure_never_formats_foreign_values():
    assert m.safe_failure(OSError("INVENTED-SECRET"))=={"code":"custody_refused","role":"leaf","changed_fields":[]}
    error=m.CustodyError(["secret"],["path"],["ctime","secret",5])
    assert m.safe_failure(error)=={"code":"custody_refused","role":"leaf","changed_fields":["ctime"]}


@pytest.mark.parametrize("root",(m.LANE_ROOT,m.PRIVATE_CUSTODY_ROOT,m.LANE_ROOT.parent/"insider_buying_sec_complete_16_9ab2ed0",Path("/Volumes")))
def test_fixture_cannot_target_actual_or_other_private_roots(root):
    with pytest.raises(m.CustodyError):m.Epoch({}, {"audit_id":"invented"},fixture=True,fixture_root=root,checker=lambda:None)


@pytest.mark.parametrize("name,role",(("failed-predecessor-snapshot.json","snapshot"),("storage-qualification.json","storage_qualification"),
    ("input-bindings.json","input_bindings"),("request-001-started.json","request_started"),("synthetic-002.json","synthetic")))
def test_controlled_diagnostic_roles_never_emit_path_or_body(name,role):
    assert m._role(name)==role
