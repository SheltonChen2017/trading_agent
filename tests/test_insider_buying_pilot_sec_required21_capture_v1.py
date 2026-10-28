"""Genuine invented source factories and isolated temporary custody only."""
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("fcntl", reason="supported macOS/POSIX custody")
from research import insider_buying_pilot_sec_required21_capture_v1 as m

CONTACT = "invented-required21@unit.test"


@pytest.fixture(scope="module")
def selected(tmp_path_factory):
    path = Path(__file__).with_name("test_insider_buying_pilot_sec_required21_selection_v1.py")
    spec = importlib.util.spec_from_file_location("invented_required21_capture_source", path)
    helper = importlib.util.module_from_spec(spec); spec.loader.exec_module(helper)
    corpus = helper.corpus.__wrapped__(tmp_path_factory)
    return helper._fixture_selection(corpus)


def _body(request):
    acc, form = request["accession_number"], request["form_type"]
    day, issuer = request["filing_date"].replace("-", ""), request["issuer_cik"].zfill(10)
    owner = "0000999999"
    return (f"<SEC-DOCUMENT>{acc}.txt : {day}\n<SEC-HEADER>{acc}.hdr.sgml : {day}\n"
        f"<ACCEPTANCE-DATETIME>{day}101112\n<ACCESSION-NUMBER>{acc}\n<TYPE>{form}\n<FILING-DATE>{day}\n"
        f"<REPORTING-OWNER>\n<OWNER-DATA>\n<CIK>{owner}\n<CONFORMED-NAME>Invented owner\n</OWNER-DATA>\n</REPORTING-OWNER>\n"
        f"<ISSUER>\n<COMPANY-DATA>\n<CIK>{issuer}\n</COMPANY-DATA>\n</ISSUER>\n</SEC-HEADER>\n"
        f"<DOCUMENT>\n<TYPE>{form}\n<SEQUENCE>1\n<FILENAME>ownership.xml\n<TEXT>\n"
        f"<ownershipDocument><documentType>{form}</documentType><issuer><issuerCik>{issuer}</issuerCik></issuer>"
        f"<reportingOwner><reportingOwnerId><rptOwnerCik>{owner}</rptOwnerCik></reportingOwnerId></reportingOwner>"
        "</ownershipDocument>\n</TEXT>\n</DOCUMENT>\n</SEC-DOCUMENT>\n").encode()


def _response(raw):
    return m.first.SecHttpResult(200, (("Content-Type", "text/plain"), ("Content-Length", str(len(raw)))), raw)


class Clock:
    def __init__(self):self.now = 0; self.sleeps = []
    def tick(self):return self.now
    def sleep(self, duration):self.sleeps.append(duration); self.now += round(duration*1e9)


def _run(selected, tmp_path, **changes):
    plan = selected.to_payload(); by_url = {row["request"]["url"]:row["request"] for row in plan["requests"]}
    calls = []; clock = Clock(); root = tmp_path/"new-scope"
    def transport(url, headers, maximum):
        calls.append(url)
        assert maximum == m.MAX_PARENT_BYTES and headers["Accept-Encoding"] == "identity"
        return _response(_body(by_url[url]))
    arguments = dict(root=root, transport=transport, contact=CONTACT, clock=lambda:"2026-10-28T00:00:00Z",
        monotonic_ns=clock.tick, sleep=clock.sleep)
    arguments.update(changes)
    result = m.run_invented(selected, **arguments)
    return result, root, calls, clock


def _read(root, name):return json.loads((root/name).read_bytes())


def test_genuine_first8_capture_claims_originals_once_and_keeps_model_not_PIT(selected, tmp_path):
    result, root, calls, clock = _run(selected, tmp_path)
    assert result["planned"] == result["started"] == len(calls) == 8 and result["unattempted"] == 0
    assert result["completed_without_refusal"] is True
    assert len(clock.sleeps) == 8 and all(value == .5 for value in clock.sleeps)
    plan = selected.to_payload(); final = _read(root, "complete.json"); index = _read(root, "consumed-index.json")
    assert calls == [row["request"]["url"] for row in plan["requests"]]
    assert len(index["accessions"]) == len(plan["consumed_accessions"])+8
    assert index["previous_index_sha256"] == plan["consumption_sha256"]
    assert index["unknown_prior_archive_memberships_remain_unknown"] is True
    for ordinal, item in enumerate(final["results"]):
        row = _read(root, item["result_name"]); start = _read(root, item["start_name"])
        claim = _read(root/"claims", item["claim_name"])
        assert row["claim_sha256"] == item["claim_sha256"] == m._sha(m._raw(claim))
        assert row["start_sha256"] == item["start_sha256"] == m._sha(m._raw(start))
        assert start["ordinal"] == ordinal and start["attempt"] == claim["attempt"] == row["attempt"] == 1
        checked = row["inspection"]; raw = (root/"objects"/row["body_object"]).read_bytes()
        assert checked["privacy_cleared"] is checked["structure_bound"] is True and checked["code"] == "none"
        for field in ("header", "primary_xml"):
            child = checked["projection"][field]
            assert m._sha(raw[child["offset"]:child["offset"]+child["bytes"]]) == child["sha256"]
        assert checked["projection"]["accepted_at_raw_uninterpreted"].endswith("101112")
        assert row["transport_invocations"] == 1 and row["remote_request_count_measured"] is False
    assert all(value is False if type(value) is bool else value == 0 for value in result["authority"].values())
    assert all(CONTACT.encode() not in path.read_bytes() for path in root.rglob("*.json"))
    assert m._sha((root/"complete.json").read_bytes()) == result["complete_sha256"]


@pytest.mark.parametrize("kind", ["HTTP", "transport", "XML", "header", "privacy", "native"])
def test_first_refusal_consumes_one_claim_preserves_suffix_and_never_retries(selected, tmp_path, kind):
    request = selected.to_payload()["requests"][0]["request"]; raw = _body(request); calls = []
    if kind == "XML":raw = raw.replace(b"<ownershipDocument>", b"<wrongDocument>")
    if kind == "header":raw = raw.replace(b"<ACCESSION-NUMBER>", b"<WRONG-ACCESSION>")
    if kind == "privacy":raw += CONTACT.encode()
    def transport(*args):
        calls.append(args[0])
        if kind == "transport":raise OSError("PRIVATE TRANSPORT ERROR")
        return m.first.SecHttpResult(403, (), b"") if kind == "HTTP" else _response(raw)
    def refused(*args):raise RuntimeError("PRIVATE NATIVE ERROR")
    result, root, _, _ = _run(selected, tmp_path, transport=transport, **({"inspect":refused} if kind == "native" else {}))
    assert len(calls) == result["started"] == 1 and result["unattempted"] == 7
    assert result["completed_without_refusal"] is False
    assert len(_read(root, "consumed-index.json")["accessions"]) == len(selected.to_payload()["consumed_accessions"])+1
    terminal = _read(root, "request-000-result.json")
    assert terminal["code"] == {"HTTP":"HTTP_non200", "transport":"transport_ambiguous", "XML":"original_structure_refused",
        "header":"original_structure_refused", "privacy":"finite_privacy_refused", "native":"inspection_refused"}[kind]
    assert bool(list((root/"objects").iterdir())) is (kind in {"XML", "header"})
    assert b"PRIVATE" not in (root/"request-000-result.json").read_bytes()


def test_non200_body_cannot_be_hashed_or_passed_to_inspection(selected, tmp_path):
    with pytest.raises(m.Required21CaptureError, match="HTTP_framing_refused"):
        _run(selected, tmp_path, transport=lambda *args:m.first.SecHttpResult(403, (), b"unqualified body"),
            inspect=lambda *args:pytest.fail("non200 reached inspection"))


def test_privacy_failure_precedes_every_body_hash_and_projection(selected, monkeypatch):
    request = selected.to_payload()["requests"][0]["request"]; raw = _body(request)+CONTACT.encode()
    original = m._sha
    monkeypatch.setattr(m, "_sha", lambda value:pytest.fail("body hashed before privacy") if value == raw else original(value))
    monkeypatch.setattr(m, "project_sec_complete_submission", lambda *args:pytest.fail("projection before privacy"))
    checked = m._inspect(raw, _response(raw).headers, CONTACT, request)
    assert checked["code"] == "finite_privacy_refused" and checked["privacy_cleared"] is False
    assert checked["body_sha256"] is checked["headers_sha256"] is None


def test_fresh_scope_refuses_even_existing_empty_directory_before_contact(selected, tmp_path):
    root = tmp_path/"new-scope"; root.mkdir(mode=0o700)
    with pytest.raises(m.Required21CaptureError, match="namespace_consumed"):
        _run(selected, tmp_path, contact=lambda:pytest.fail("contact reached on consumed namespace"))
    assert list(root.iterdir()) == []


def test_capacity_refuses_before_private_contact_or_claim(selected, tmp_path):
    with pytest.raises(m.Required21CaptureError, match="capacity_refused"):
        _run(selected, tmp_path, free_bytes=lambda:0, contact=lambda:pytest.fail("contact before capacity"))
    assert list((tmp_path/"new-scope"/"claims").iterdir()) == []


def test_fixture_root_fence_precedes_opening_actual_namespace(selected, monkeypatch):
    monkeypatch.setattr(m, "_Namespace", lambda *args:pytest.fail("actual root reached as fixture"))
    with pytest.raises(ValueError):m.run_invented(selected, root=m.LANE_ROOT.joinpath(*m.ARTIFACT_PARTS), transport=lambda *args:None)


def test_undersleep_cannot_dispatch_and_consumed_claim_is_preserved(selected, tmp_path):
    with pytest.raises(m.Required21CaptureError, match="spacing_refused"):_run(selected, tmp_path, sleep=lambda _:None)
    assert len(list((tmp_path/"new-scope"/"claims").iterdir())) == 1
    assert not list((tmp_path/"new-scope").glob("request-*-start.json"))


def test_constructor_cannot_self_authorize_actual_transport(selected, monkeypatch):
    plan = selected.to_payload(); auth = m._Authorization({}, plan, lambda:None)
    context = m._Dispatch(auth, 0, plan["requests"][0]["request"], {}, lambda:None, lambda:None)
    monkeypatch.setattr(m.http.client, "HTTPSConnection", lambda *args, **kwargs:pytest.fail("unauthorized opener reached"))
    with pytest.raises(m.Required21CaptureError, match="genuine_dispatch_required"):m._transport(context)


def test_command_requires_initial_four_native_denials_and_isolated_runtime():
    command = " ".join(m._command("select", {}))
    for marker in ("deny network*", "deny process-fork", "deny file-write*", 'deny process-exec (literal "/usr/bin/security")', "-I", "-S", "-B", "pycache_prefix="):
        assert marker in command


def test_worker_source_refusal_precedes_private_input_and_memory_cleanup(monkeypatch):
    events = []
    monkeypatch.setattr(m.previous, "_isolated", lambda:events.append("flags"))
    monkeypatch.setattr(m.base, "_prove_isolation", lambda:events.append("four-denials"))
    monkeypatch.setattr(m.previous, "_WorkerMemoryGuard", lambda:SimpleNamespace(check=lambda:None, close=lambda:events.append("closed")))
    def changed(identity):events.append("source"); raise m.Required21CaptureError("source_changed")
    monkeypatch.setattr(m, "_current", changed)
    monkeypatch.setattr(m.source, "_SourceInputs", lambda *args:pytest.fail("source refusal opened actual input"))
    assert m._worker("select", {}) == {"ok":False, "code":"source_changed"}
    assert events == ["flags", "four-denials", "source", "closed"]


def test_cli_protects_echo_before_argument_parsing_and_sanitizes_private_errors(monkeypatch, capsys):
    events = []
    monkeypatch.setattr(m.contact_io, "_protect_stdin_echo", lambda:events.append("protected") or "saved")
    monkeypatch.setattr(m.contact_io, "_restore_stdin_echo", lambda saved:events.append(("restored", saved)))
    assert m.main(["--PRIVATE-ARGUMENT"]) == 2
    assert events == ["protected", ("restored", "saved")]
    assert "PRIVATE" not in capsys.readouterr().out


@pytest.mark.parametrize("field,value", [("body_bytes", True), ("body_sha256", "a"*64), ("headers_sha256", "b"*64), ("privacy_cleared", 1)])
def test_private_inspector_cannot_forge_hash_or_type_link(selected, field, value):
    request = selected.to_payload()["requests"][0]["request"]; raw = _body(request); headers = _response(raw).headers
    checked = m._inspect(raw, headers, CONTACT, request); checked[field] = value
    with pytest.raises(m.Required21CaptureError, match="inspection_refused"):m._inspection_valid(checked, raw, headers)


def test_readback_replays_complete_original_structure_and_preserves_privacy_limit(selected, tmp_path):
    result, root, _, _ = _run(selected, tmp_path)
    observed = m._readback(root, result["complete_sha256"], fixture=True)
    assert observed["retained_bodies"] == observed["structurally_bound_bodies"] == observed["started"] == 8
    assert observed["original_contact_privacy_rescreened"] is False and observed["new_requests"] == 0
    assert observed["completed_without_refusal"] is True


@pytest.mark.parametrize("target", ["body", "claim", "start", "inspection", "extra", "index"])
def test_readback_refuses_any_changed_or_extra_custody_leaf(selected, tmp_path, target):
    result, root, _, _ = _run(selected, tmp_path)
    if target == "body":path = next((root/"objects").iterdir())
    elif target == "claim":path = next((root/"claims").iterdir())
    elif target == "start":path = root/"request-000-start.json"
    elif target == "inspection":path = root/"request-000-result.json"
    elif target == "index":path = root/"consumed-index.json"
    else:path = root/"unknown.json"; path.write_bytes(b"{}")
    if target != "extra":path.write_bytes(path.read_bytes()+b" ")
    with pytest.raises(ValueError):m._readback(root, result["complete_sha256"], fixture=True)


@pytest.mark.parametrize("change", [lambda p:p.update(private_value="PRIVATE"), lambda p:p.update(reporting_owner_count=True),
    lambda p:p["header"].update(offset=True), lambda p:p["primary_xml"].update(bytes=0),
    lambda p:p["primary_xml"].update(sha256="f"*64), lambda p:p.update(amendment_lineage_inferred=True)])
def test_projection_metadata_is_closed_typed_and_exact_child_bound(selected, change):
    request = selected.to_payload()["requests"][0]["request"]; raw = _body(request); headers = _response(raw).headers
    checked = m._inspect(raw, headers, CONTACT, request)
    assert checked["structure_bound"] is True
    change(checked["projection"])
    with pytest.raises(m.Required21CaptureError, match="inspection_refused"):m._inspection_valid(checked, raw, headers)


def _dispatch(selected, monkeypatch, response=None, *, expire=False, cleanup=False):
    events = []; plan = selected.to_payload(); request = plan["requests"][0]["request"]
    def guard():events.append("controller_held_and_inputs_checked")
    def durable():events.append("durable_claim_start")
    auth = m._Authorization({}, plan, guard)
    # Invented runtime registry seam only. Constructors themselves grant no
    # authority; native OS denial still prevents every external connection.
    m._AUTH[auth] = (id(auth.identity), id(plan), id(guard), auth.plan_sha256)
    headers = {"Accept-Encoding":"identity"}
    context = m._Dispatch(auth, 0, request, headers, guard, durable)
    m._DISPATCH[context] = (id(auth), 0, id(request), m._raw(headers), id(guard), id(durable))
    monkeypatch.setattr(m.batch, "_lane_boundary", lambda identity:events.append("exact_lane_metadata"))
    class Connection:
        def __init__(self, host, timeout):
            assert events == ["controller_held_and_inputs_checked", "durable_claim_start", "exact_lane_metadata"]
            assert host == "www.sec.gov" and timeout == 15; events.append("connection")
        def request(self, method, path, headers):
            assert method == "GET" and path == request["url"].removeprefix("https://www.sec.gov")
            events.append("GET")
            if expire:raise m._Deadline()
        def getresponse(self):return response
        def close(self):
            events.append("closed")
            if cleanup:raise OSError("PRIVATE CLEANUP DETAIL")
    monkeypatch.setattr(m.http.client, "HTTPSConnection", Connection)
    return context, events


def test_actual_transport_checks_controller_and_durable_start_before_one_GET_and_forbids_replay(selected, monkeypatch):
    request = selected.to_payload()["requests"][0]["request"]; raw = _body(request); reads = []
    response = SimpleNamespace(status=200, getheaders=lambda:_response(raw).headers,
        read=lambda maximum:reads.append(maximum) or raw)
    context, events = _dispatch(selected, monkeypatch, response)
    result = m._transport(context)
    assert result.body == raw and reads == [len(raw)] and events[-1] == "closed"
    assert events.count("GET") == 1 and context.invoked is True
    with pytest.raises(m.Required21CaptureError, match="genuine_dispatch_required"):m._transport(context)


def test_actual_transport_non200_headers_and_body_remain_unread(selected, monkeypatch):
    response = SimpleNamespace(status=403, getheaders=lambda:pytest.fail("non200 headers consumed"),
        read=lambda *args:pytest.fail("non200 body consumed"))
    context, events = _dispatch(selected, monkeypatch, response)
    result = m._transport(context)
    assert result.status == 403 and result.body == b"" and result.headers == () and events[-1] == "closed"


def test_actual_transport_bad_framing_refuses_before_body_read(selected, monkeypatch):
    response = SimpleNamespace(status=200, getheaders=lambda:(("Content-Length", str(m.MAX_PARENT_BYTES+1)),),
        read=lambda *args:pytest.fail("oversize framing read a body"))
    context, events = _dispatch(selected, monkeypatch, response)
    with pytest.raises(m.Required21CaptureError, match="HTTP_framing_refused"):m._transport(context)
    assert events[-1] == "closed"


def test_actual_transport_deadline_restores_timer_and_handler_and_keeps_attempt_consumed(selected, monkeypatch):
    old_handler = m.signal.getsignal(m.signal.SIGALRM)
    context, events = _dispatch(selected, monkeypatch, expire=True)
    with pytest.raises(m.Required21CaptureError, match="transport_deadline"):m._transport(context)
    assert m.signal.getsignal(m.signal.SIGALRM) == old_handler and m.signal.getitimer(m.signal.ITIMER_REAL) == (0., 0.)
    assert context.authorization.attempted == {0} and context.invoked is True and events[-1] == "closed"


def test_actual_transport_cleanup_refusal_is_finite_and_attempt_remains_consumed(selected, monkeypatch):
    request = selected.to_payload()["requests"][0]["request"]; raw = _body(request)
    response = SimpleNamespace(status=200, getheaders=lambda:_response(raw).headers, read=lambda maximum:raw)
    context, events = _dispatch(selected, monkeypatch, response, cleanup=True)
    with pytest.raises(m.Required21CaptureError, match="^cleanup_refused$"):m._transport(context)
    assert context.authorization.attempted == {0} and context.invoked is True and events[-1] == "closed"


def test_honest_cleanup_refusal_keeps_one_claim_and_replays_as_failed_completion(selected, tmp_path):
    def refused(*args):raise m.Required21CaptureError("cleanup_refused")
    result, root, _, _ = _run(selected, tmp_path, transport=refused)
    assert result["started"] == 1 and result["unattempted"] == 7 and result["completed_without_refusal"] is False
    terminal = _read(root, "request-000-result.json")
    assert terminal["code"] == "cleanup_refused" and terminal["transport_invocations"] == 1
    assert terminal["http_status"] is terminal["inspection"] is terminal["body_object"] is None
    observed = m._readback(root, result["complete_sha256"], fixture=True)
    assert observed["completed_without_refusal"] is False and observed["retained_bodies"] == 0 and observed["started"] == 1


def test_controller_lock_refusal_precedes_source_inputs_namespace_and_transport(monkeypatch):
    monkeypatch.setattr(m, "_identity", lambda head:{"head":head})
    def denied(root, *, create):assert create is False; raise OSError("PRIVATE LOCK FAILURE")
    monkeypatch.setattr(m.batch.campaign, "Controller", denied)
    monkeypatch.setattr(m.batch, "SourceHold", lambda *args:pytest.fail("source hold before controller EX"))
    monkeypatch.setattr(m, "_Namespace", lambda *args:pytest.fail("namespace before controller EX"))
    monkeypatch.setattr(m, "_child", lambda *args:pytest.fail("source parse before controller EX"))
    with pytest.raises(m.Required21CaptureError, match="^native_refused$"):m.run_actual(expected_head="a"*40)


def test_existing_cooperative_controller_stays_exclusive_through_each_capture(selected, tmp_path):
    old_root = tmp_path/"invented-existing-controller"; old_root.mkdir(mode=0o700)
    controller = m.batch.campaign.Controller(old_root, create=True, fixture=True)
    by_url = {row["request"]["url"]:row["request"] for row in selected.to_payload()["requests"]}
    calls = []
    def transport(url, headers, maximum):
        controller.check()
        with pytest.raises(BlockingIOError):m.batch.campaign.Controller(old_root, create=False, fixture=True)
        calls.append(url); return _response(_body(by_url[url]))
    try:
        result, _, _, _ = _run(selected, tmp_path, transport=transport, guard=controller.check)
        assert result["started"] == len(calls) == 8
        controller.check()
    finally:controller.close()
    after = m.batch.campaign.Controller(old_root, create=False, fixture=True); after.close()


def test_actual_source_setup_failure_releases_existing_controller_without_contact(monkeypatch):
    events = []; monkeypatch.setattr(m, "_identity", lambda head:{"head":head})
    class Controller:
        def __init__(self, root, *, create):assert create is False; events.append("EX")
        def close(self):events.append("released")
    monkeypatch.setattr(m.batch.campaign, "Controller", Controller)
    def refused(identity):events.append("source"); raise m.Required21CaptureError("source_changed")
    monkeypatch.setattr(m.batch, "SourceHold", refused)
    monkeypatch.setattr(m.contact_io, "_stdin_contact", lambda:pytest.fail("source setup reached contact"))
    with pytest.raises(m.Required21CaptureError, match="source_changed"):m.run_actual(expected_head="a"*40)
    assert events == ["EX", "source", "released"]


@pytest.mark.parametrize("field,value", [("transport_invocations",0), ("transport_invocations",True),
    ("http_status",403), ("http_status",True), ("attempt",True), ("ordinal",False),
    ("finished_utc","2026-10-28T00:00:00"), ("code","HTTP_non200")])
def test_coherently_reanchored_impossible_terminal_cannot_pass_readback(selected, tmp_path, field, value):
    _, root, _, _ = _run(selected, tmp_path)
    terminal = _read(root, "request-000-result.json"); terminal[field] = value
    raw = m._raw(terminal); (root/"request-000-result.json").write_bytes(raw)
    complete = _read(root, "complete.json"); complete["results"][0]["result_sha256"] = m._sha(raw)
    complete_raw = m._raw(complete); (root/"complete.json").write_bytes(complete_raw)
    with pytest.raises(ValueError):m._readback(root, m._sha(complete_raw), fixture=True)


def test_direct_fixture_core_proves_native_denial_before_private_contact(selected, tmp_path, monkeypatch):
    root = tmp_path/"direct-fixture"; ns = m._Namespace(root)
    def denied():raise m.Required21CaptureError("native_refused")
    monkeypatch.setattr(m.first, "_native_fixture_denial", denied)
    try:
        with pytest.raises(m.Required21CaptureError, match="native_refused"):
            m._capture(ns, selected.to_payload(), {}, fixture=True, contact=lambda:pytest.fail("private input before native"),
                guard=lambda:None, inspect=m._inspect, transport=lambda *args:None)
    finally:ns.close()


@pytest.mark.parametrize("raw", [b'{}', b'{}\nPRIVATE', b'x'*(m.MAX_CONTROL+1)])
def test_private_stdin_frame_requires_exact_bounded_LF_control(raw, monkeypatch):
    monkeypatch.setattr(m.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(raw)))
    if raw == b'{}\nPRIVATE':
        assert m._private_line() == {}
    else:
        with pytest.raises(ValueError):m._private_line()


# Claude review section 341 (IBREQ21-CR34101): a capture cut back to a
# structure-bound prefix, with the later leaves removed and the index and
# complete re-pinned, must not pass readback.
def test_readback_refuses_a_coherently_truncated_capture_without_a_final_refusal(selected, tmp_path):
    result, root, _, _ = _run(selected, tmp_path)
    final = _read(root, "complete.json"); plan = selected.to_payload(); keep = 3
    for item in final["results"][keep:]:
        terminal = _read(root, item["result_name"])
        for leaf in (root/"claims"/item["claim_name"], root/item["start_name"], root/item["result_name"],
                     root/item["result_name"].replace("-result.json", "-headers.json"), root/"objects"/terminal["body_object"]):
            leaf.unlink()
    final["results"] = final["results"][:keep]
    index = _read(root, "consumed-index.json")
    index["accessions"] = sorted(set(plan["consumed_accessions"]) | {item["accession_number"] for item in final["results"]})
    raw = m._raw(index); (root/"consumed-index.json").write_bytes(raw); final["index_sha256"] = m._sha(raw)
    final.update(started=keep, unattempted=final["planned"]-keep, completed_without_refusal=False)
    raw = m._raw(final); (root/"complete.json").write_bytes(raw)
    with pytest.raises(m.Required21CaptureError, match="^inputs_changed$"):
        m._readback(root, m._sha(raw), fixture=True)
