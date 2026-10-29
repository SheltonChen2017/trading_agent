"""Independent invented-only stat/IPC/privacy boundary probes."""
from __future__ import annotations

import copy
import gzip
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("fcntl", reason="IBWIN-CR01: POSIX custody support; Windows custody port deferred")
from research import insider_buying_sec_feed_nc_source_binding_observe_v1 as m


CONTACT = "invented-binding-peer@unit.test"


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    path = Path(__file__).with_name("test_insider_buying_sec_feed_nc_source_binding_v1.py")
    spec = importlib.util.spec_from_file_location("invented_binding_peer_fixture", path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    return helper.corpus.__wrapped__(tmp_path_factory)


def _identity():
    ancestor = m.inherited.inherited
    campaign = m.previous.batch.campaign
    sources = {name:"a"*64 for name in (ancestor.SELF_PATH, ancestor.TEST_PATH,
        campaign.SELF_PATH, campaign.TEST_PATH, campaign.CAPTURE_SOURCE_PATH, campaign.CAPTURE_TEST_PATH,
        m.selector.SELF_PATH, m.selector.PURE_PATH)}
    return {"root":str(m.LANE_ROOT), "branch":m.LANE_BRANCH, "head":"a"*40,
        "clean":True, "source_sha256":sources, "source_inventory_sha256":m._sha(m._raw(sources))}


def _source_metadata(corpus):
    summary = copy.deepcopy(corpus[2].to_payload())
    summary.update(fixture_only=False, intake_manifest_sha256=m.selector.pure.census.RETAINED_ZIP_MANIFEST_SHA256,
        selection_sha256=m.prior.ACTUAL_ANCHORS.selection)
    selected = {row["period"]:row for row in corpus[1][2]["quarters"]}
    quarters = [{key:row[key] for key in ("period", *m.binder.roster.STAT_KEYS, "source_form_counts", "zip_sha256")}
        | {"selected_affected":selected[row["period"]]["selected_affected"]} for row in summary["quarters"]]
    pilot = [row for row in quarters if row["period"] in m.binder.roster.PILOT_PERIODS]
    accepted = {"accepted_selection_sha256":m.prior.ACTUAL_ANCHORS.selection,
        "accepted_complete_sha256":m.prior.ACTUAL_ANCHORS.selector_complete,
        "actual_success_observer_final_sha256":m.prior.ACTUAL_ANCHORS.observer_final,
        "failed_predecessor_promoted":False, "source_capture_window":"2006Q1..2026Q2",
        "audit_quarter_window":"2020Q1..2026Q1", "quarters":quarters, "pilot_quarter_count":20,
        "pilot_counts":{key:sum(row[key] for row in pilot) for key in m.binder.roster.STAT_KEYS},
        "pilot_form_counts":copy.deepcopy(summary["pilot_form_counts"]),
        "pilot_affected_periods":[row["period"] for row in pilot if row["selected_affected"]],
        "raw_zip_or_submission_rows_decoded_here":False, "original_parent_admission_established_here":False}
    return {"schema":m.SCHEMA+"/source-inputs", "accepted_selector":accepted,
        "selector_execution_identity":_identity(),
        "intake_manifest_sha256":m.selector.pure.census.RETAINED_ZIP_MANIFEST_SHA256,
        "intake_leaf_count":84, "intake_ZIP_count":82, "retained_source_roster":summary,
        "consumed_control_pins":dict(m.previous.CONSUMED_PINS), "consumed_count":20044,
        "consumed_index_sha256":m.previous.CONSUMED_PINS["consumed-index.json"],
        "consumed_execution_identity":_identity(), "consumed_planner_receipt":{
            "plan_sha256":m.previous.CONSUMED_PINS["plan.json"], "complete_sha256":"c"*64, "execution_identity":_identity()},
        "raw_prefix_and_ZIP_body_bytes_read":0, "ZIP_body_hashes_verified_here":False,
        "old_original_parent_body_bytes_read":0, "unknown_prior_archive_memberships_remain_unknown":True}


def _intake(corpus, tmp_path):
    _, supplied, _, _ = corpus
    manifest, images, _ = supplied
    root = tmp_path/"invented-intake"
    root.mkdir(mode=0o700)
    name = m.selector.pure.census._MANIFEST_NAME
    (root/name).write_bytes(manifest)
    auxiliary = b"invented opaque auxiliary control\n"
    (root/m.selector._AUX_NAME).write_bytes(auxiliary)
    bindings = m.selector.pure.census._manifest_bindings(manifest)
    for binding, image in zip(bindings, images, strict=True):
        (root/binding.filename).write_bytes(image.raw_bytes)
    return root, (m._sha(manifest), len(manifest)), (m._sha(auxiliary), len(auxiliary))


def test_review_genuine_metadata_hold_reads_no_ZIP_bytes_or_hashes(corpus, tmp_path, monkeypatch):
    root, manifest_pin, auxiliary_pin = _intake(corpus, tmp_path)
    held_io = m.selector.held_io
    original_open, original_hash = held_io._HeldCapture.open, held_io._hash_stream
    zip_inodes = {(path.stat().st_dev, path.stat().st_ino) for path in root.glob("*.zip")}
    opened = []
    class Stream:
        def __init__(self, value, name): self.value, self.name = value, name
        def read(self, *args):
            assert not self.name.endswith(".zip"), "ZIP bytes read in metadata preflight"
            return self.value.read(*args)
        def __getattr__(self, name): return getattr(self.value, name)
    def opened_guard(self, name, cap):
        value = original_open(self, name, cap)
        opened.append(name)
        return Stream(value, name)
    def hash_guard(stream, cap):
        st = os.fstat(stream.fileno())
        assert (st.st_dev, st.st_ino) not in zip_inodes, "ZIP body hashed in metadata preflight"
        return original_hash(stream, cap)
    monkeypatch.setattr(held_io._HeldCapture, "open", opened_guard)
    monkeypatch.setattr(held_io, "_hash_stream", hash_guard)
    monkeypatch.setattr(m.selector, "_HeldIntake", lambda *a, **k: pytest.fail("full intake constructed in preflight"))
    hold = m._IntakeMetadata(fixture=True, root=root, manifest_pin=manifest_pin, auxiliary_pin=auxiliary_pin)
    try:
        hold.check()
        assert len([name for name in opened if name.endswith(".zip")]) == 82
        assert len(hold.tree.handles) == 84
    finally: hold.close()


def test_review_metadata_intake_preserves_strict_old_ctime_and_inventory(corpus, tmp_path):
    root, manifest_pin, auxiliary_pin = _intake(corpus, tmp_path)
    hold = m._IntakeMetadata(fixture=True, root=root, manifest_pin=manifest_pin, auxiliary_pin=auxiliary_pin)
    try:
        path = next(root.glob("*.zip"));before = path.stat()
        mode = before.st_mode & 0o777
        path.chmod(0o600 if mode != 0o600 else 0o644);path.chmod(mode)
        assert path.stat().st_size == before.st_size and path.stat().st_mtime_ns == before.st_mtime_ns
        assert path.stat().st_ctime_ns != before.st_ctime_ns
        with pytest.raises(ValueError): hold.check()
    finally: hold.close()


def test_review_actual_root_fixture_refuses_before_any_metadata_reader(monkeypatch):
    monkeypatch.setattr(m.selector.held_io, "_HeldCapture", lambda *a, **k: pytest.fail("actual root opened as fixture"))
    with pytest.raises(ValueError):
        m._IntakeMetadata(fixture=True, root=m.LANE_ROOT, manifest_pin=("a"*64,1), auxiliary_pin=("b"*64,1))


@pytest.mark.parametrize("slot", ["retained_source_roster", "accepted_selector", "consumed_planner_receipt"])
def test_review_nested_source_controls_cannot_export_extra_private_fields(corpus, slot):
    value = _source_metadata(corpus)
    m._source_metadata_valid(value)
    value[slot]["unregistered_private_value"] = CONTACT
    with pytest.raises(ValueError): m._source_metadata_valid(value)


def _prefix(body):
    header = bytearray(512)
    name = b"invented-not-a-route.nc"
    header[:len(name)] = name
    header[124:136] = format(len(body), "011o").encode()+b"\0"
    header[148:156] = b"        ";header[156:157] = b"0";header[257:265] = b"ustar  \0"
    header[148:156] = format(sum(header), "06o").encode()+b"\0 "
    raw = gzip.compress(bytes(header)+body+bytes((-len(body))%512)+bytes(1024)+bytes(range(256))*500, compresslevel=0, mtime=0)[:65536]
    assert len(raw) == 65536
    return raw


def test_review_prefix_privacy_refusal_precedes_genuine_ZIP_reader_and_source_hash(monkeypatch):
    raw = _prefix(b"<SUBMISSION>\n"+CONTACT.encode()+b"\n</SUBMISSION>\n")
    prefix = SimpleNamespace(read_body=lambda:raw, root=Path("/invented-only-not-opened"), pins={"complete.json":"a"*64})
    monkeypatch.setattr(m.capture, "_verify_files", lambda *a, **k: {"invented_replay":"not source proof"})
    monkeypatch.setattr(m.selector, "_HeldIntake", lambda *a, **k: pytest.fail("ZIP reader preceded complete prefix privacy"))
    original = m._sha
    monkeypatch.setattr(m, "_sha", lambda value:pytest.fail("raw prefix hashed before privacy") if value == raw else original(value))
    with pytest.raises(ValueError): m._analyse({}, CONTACT, prefix, None, {}, fixture=True)


@pytest.mark.parametrize("mutation", ["decoded_before_first_header", "more_collected_than_headers"])
def test_review_geometry_cannot_claim_impossible_header_or_candidate_population(mutation):
    _, geometry = m._collect(_prefix(b"<SUBMISSION>\n</SUBMISSION>\n"), CONTACT, True)
    m._geometry_valid(geometry)
    if mutation == "decoded_before_first_header": geometry["decoded_prefix_bytes"] = 0
    else: geometry["candidate_payloads_collected"] = geometry["physical_headers_observed"]+1
    with pytest.raises(ValueError): m._geometry_valid(geometry)


def test_review_worker_native_source_checks_precede_every_private_metadata_hold(monkeypatch):
    events = []
    monkeypatch.setattr(m.previous, "_isolated", lambda:events.append("flags"))
    monkeypatch.setattr(m.source_runner, "_prove_isolation", lambda:events.append("native"))
    monkeypatch.setattr(m.previous, "_WorkerMemoryGuard", lambda:SimpleNamespace(check=lambda:None,close=lambda:None))
    def changed(identity):
        events.append("current")
        raise m.NCBindingObserveError("source_changed")
    monkeypatch.setattr(m, "_current", changed)
    monkeypatch.setattr(m.capture, "_compile_sources", lambda *a:pytest.fail("compile preceded current source"))
    monkeypatch.setattr(m.inherited.inherited, "_HeldPrefix", lambda *a:pytest.fail("private metadata preceded source"))
    monkeypatch.setattr(m, "_SourceInputs", lambda *a:pytest.fail("private intake preceded source"))
    assert m._worker("preflight", {}) == {"ok":False,"refusal":{"phase":"source","code":"source_changed"}}
    assert events == ["flags", "native", "current"]
