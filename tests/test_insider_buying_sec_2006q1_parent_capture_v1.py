"""Activated collector tests: invented sources, OS network denial external."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import importlib.util
import json
import errno
import os
import io
from pathlib import Path
import sys

import pytest

pytest.importorskip("fcntl", reason="IBWIN-CR01: macOS/POSIX custody supported")
pytest.importorskip("termios", reason="IBWIN-CR01: macOS/POSIX private input supported")

LANE = Path("/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__insider_buying")
sys.path.insert(0, str(LANE / "tests"))
from test_insider_buying_sec_complete_submission import _complete, _legacy_header

SOURCE = LANE / "research/insider_buying_sec_2006q1_parent_capture_v1.py"
spec = importlib.util.spec_from_file_location("ib_early_capture_private_draft", SOURCE)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _raw(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _request(ordinal):
    accession = f"0000000123-06-{ordinal:06d}"
    path = f"edgar/data/987654/{accession}.txt"
    return {"period": "2006Q1", "accession_number": accession, "form_type": "4", "filing_date": "2006-01-03",
        "issuer_cik": "0000123456", "archive_path": path, "url": "https://www.sec.gov/Archives/" + path,
        "source_record_ordinal": ordinal, "accession_key_sha256": _sha(accession.encode()),
        **{name: "a" * 64 for name in ("filing_metadata_sha256", "submission_inventory_sha256", "quarterly_zip_sha256",
            "submission_member_sha256", "master_decoded_sha256", "master_receipt_sha256")}}


def _accounting():
    prefix = [_request(ordinal) for ordinal in range(1, 65)]
    return {"schema": module.bootstrap.locators.SCHEMA, "authority": module.bootstrap.locators._authority(),
        "prefix": prefix, "maximum_prefix": 64, "prefix_sha256": _sha(_raw(prefix)),
        "prior_exposure_inventory_sha256": "d" * 64, "source_filings": 70,
        "counts": {"target_filings": 64, "context_filings": 6},
        "form_counts": {"3": 2, "3/A": 1, "4": 64, "4/A": 0, "5": 2, "5/A": 1}}


def _selection(body=None):
    raw = _raw(_accounting() if body is None else body)
    return module.build_invented_selection(raw, expected_accounting_sha256=_sha(raw))


class _Ticks:
    def __init__(self):
        self.value = 0

    def __call__(self):
        self.value += module.MIN_COMPLETION_INTERVAL_NS
        return self.value


def _prior(selection, *, exposed=(), recheck=lambda: None):
    body = selection.to_payload()
    return lambda: {"snapshot_sha256": body["prior_exposure_snapshot_sha256"],
        "exposure_sha256": body["prior_exposure_inventory_sha256"], "exposed_accessions": exposed,
        "recheck": recheck, "close": lambda: None}


def _body(request):
    return _complete(header=_legacy_header()).replace(b"0000999999-22-000001", request["accession_number"].encode()).replace(
        b"20221107", b"20060103")


def _wire(selection, *, response=None, calls=None):
    by_url = {row["request"]["url"]: row["request"] for row in selection.to_payload()["requests"]}
    def wire(url, headers, cap):
        if calls is not None:
            calls.append((url, cap))
        if response is not None:
            return response(url, headers) if callable(response) else response
        raw = _body(by_url[url])
        return module.SecHttpResult(200, (("Content-Length", str(len(raw))),), raw)
    return wire


def _run(tmp_path, *, selection=None, transport=None, response=None, calls=None, capture_id="ib-sec-2006q1-initial64-invented", **kwargs):
    selection = _selection() if selection is None else selection
    return module.run_invented_capture(selection, capture_id, root=tmp_path,
        transport=_wire(selection, response=response, calls=calls) if transport is None else transport,
        prior_open=_prior(selection), clock=lambda: "2026-10-14T00:00:00Z", monotonic_ns=_Ticks(),
        sleep=lambda _: None, free_bytes=lambda: module.MIN_FREE_BYTES + 64 * module.MAX_PARENT_BYTES,
        **kwargs)


def _namespace(tmp_path):
    return tmp_path.joinpath(*module.ARTIFACT_PARTS)


def test_successful_fixture_custody_is_not_full_projection_or_admission(tmp_path):
    calls = []
    result = _run(tmp_path, calls=calls)
    assert len(calls) == result["started_requests"] == result["raw_bodies_retained"] == result["header_bound_bodies"] == 64
    assert result["fixture_only"] is True and all(value is False for value in result["authority"].values())
    report = json.loads((_namespace(tmp_path) / "runs" / result["capture_id"] / "complete.json").read_bytes())
    assert report["context_filings_not_requested"] == 6
    assert report["full_xml_projection_attempts"] == 0 and report["all_six_form_census_preserved"] is True
    assert len(list((_namespace(tmp_path) / "claims").iterdir())) == 64
    verified = module.verify_invented_capture(result["capture_id"], root=tmp_path, expected_report_sha256=result["report_sha256"])
    assert verified["header_bound_bodies"] == 64 and verified["parent_xml_projection_performed"] is False


@pytest.mark.parametrize("status", [403, 429, 404, 500])
def test_http_refusal_stops_once_only_current_claim_consumed(tmp_path, status):
    calls = []
    result = _run(tmp_path, calls=calls, response=module.SecHttpResult(status, (), b""))
    assert len(calls) == result["started_requests"] == 1
    assert result["raw_bodies_retained"] == 0 and result["planned_unclaimed_unattempted"] == 63
    assert len(list((_namespace(tmp_path) / "claims").iterdir())) == 1
    module.verify_invented_capture(result["capture_id"], root=tmp_path, expected_report_sha256=result["report_sha256"])


def test_transport_exception_start_stays_consumed_and_no_retry(tmp_path):
    calls = []
    def wire(url, headers, cap):
        calls.append(url)
        raise OSError("INVENTED PRIVATE ERROR NEVER LOG")
    result = _run(tmp_path, transport=wire)
    assert len(calls) == result["started_requests"] == 1
    report_bytes = (_namespace(tmp_path) / "runs" / result["capture_id"] / "complete.json").read_bytes()
    assert b"INVENTED PRIVATE ERROR" not in report_bytes


def test_real_route_is_disabled_when_source_is_not_the_fixed_committed_path(monkeypatch):
    monkeypatch.setattr(module, "__file__", str(LANE / "artifacts/inactive-source.py"))
    monkeypatch.setattr(module.bootstrap.custody, "_identity", lambda *args: pytest.fail("inactive path reached identity"))
    with pytest.raises(module.EarlyParentCaptureError, match="inactive_draft_not_production_source"):
        module._committed_identity("a" * 40)


def test_fixture_route_cannot_call_real_sec_transport(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("fixture reached a real SEC connection")
    monkeypatch.setattr("http.client.HTTPSConnection", forbidden)
    with pytest.raises(module.EarlyParentCaptureError, match="fixture_root_transport"):
        _run(tmp_path, transport=module._selected_sec_transport)


def test_fixture_route_cannot_touch_real_lane(tmp_path):
    with pytest.raises(module.EarlyParentCaptureError, match="fixture_root_transport"):
        module.run_invented_capture(_selection(), "ib-sec-2006q1-initial64-invented", root=LANE,
            transport=lambda *_: None, prior_open=lambda: {})


def test_just_in_time_claim_and_start_are_fsynced_before_only_request(tmp_path):
    selection = _selection()
    def wire(url, headers, cap):
        namespace = _namespace(tmp_path)
        assert len(list((namespace / "claims").iterdir())) == 1
        run = namespace / "runs/ib-sec-2006q1-initial64-invented"
        start = json.loads((run / "request-000-start.json").read_bytes())
        claim_leaf = next((namespace / "claims").iterdir())
        assert start["claim_sha256"] == _sha(claim_leaf.read_bytes())
        assert (run / "reservation.json").is_file()
        return module.SecHttpResult(403, (), b"")
    result = _run(tmp_path, selection=selection, transport=wire)
    assert result["planned_unclaimed_unattempted"] == 63


def test_existing_permanent_claim_blocks_new_capture_id_without_transport(tmp_path):
    _run(tmp_path, response=module.SecHttpResult(403, (), b""))
    calls = []
    with pytest.raises(module.EarlyParentCaptureError, match="permanent_claim_or_capture_already_exists"):
        _run(tmp_path, calls=calls, capture_id="ib-sec-2006q1-initial64-second")
    assert calls == []


def test_prior_global_exposure_blocks_before_any_new_claim(tmp_path):
    selection = _selection();accession = selection.to_payload()["requests"][0]["request"]["accession_number"]
    with pytest.raises(module.EarlyParentCaptureError, match="prefix_already_prior_exposed"):
        module.run_invented_capture(selection, "ib-sec-2006q1-initial64-invented", root=tmp_path,
            transport=lambda *_: None, prior_open=_prior(selection, exposed=[accession]))
    assert not _namespace(tmp_path).exists()


@pytest.mark.parametrize("where", ["body", "headers"])
def test_contact_echo_never_stored_hashed_or_logged(tmp_path, where):
    contact = "invented@unit.test"
    raw = b"opaque source" if where == "headers" else contact.encode()
    headers = (("Content-Length", str(len(raw))),)
    if where == "headers":
        headers += (("X-Echo", contact),)
    result = _run(tmp_path, response=module.SecHttpResult(200, headers, raw))
    assert result["started_requests"] == 1 and result["raw_bodies_retained"] == 0
    assert not list((_namespace(tmp_path) / "runs" / result["capture_id"] / "objects").iterdir())
    for path in _namespace(tmp_path).rglob("*.json"):
        assert contact.encode() not in path.read_bytes()


def test_identical_raw_responses_deduplicate_objects_without_drop_or_admission(tmp_path):
    raw = b"<unsupported>invented shared response</unsupported>"
    result = _run(tmp_path, response=module.SecHttpResult(200, (("Content-Length", str(len(raw))),), raw))
    assert result["started_requests"] == result["raw_bodies_retained"] == 64
    assert result["header_bound_bodies"] == 0
    assert len(list((_namespace(tmp_path) / "runs" / result["capture_id"] / "objects").iterdir())) == 1
    module.verify_invented_capture(result["capture_id"], root=tmp_path, expected_report_sha256=result["report_sha256"])


@pytest.mark.parametrize("form", ["3", "3/A", "5", "5/A"])
def test_context_forms_cannot_be_promoted_or_requested(form):
    body = _accounting();body["prefix"][0]["form_type"] = form;body["prefix_sha256"] = _sha(_raw(body["prefix"]))
    with pytest.raises(module.EarlyParentCaptureError, match="prefix_identity_or_context"):
        _selection(body)


@pytest.mark.parametrize("mutation", ["window", "url", "accession_key", "boolean_ordinal"])
def test_as_indexed_locator_and_lineage_never_guessed(mutation):
    body = _accounting();row = body["prefix"][0]
    if mutation == "window":row["filing_date"] = "2006-04-01"
    elif mutation == "url":row["url"] = row["url"].replace("987654", "123456")
    elif mutation == "accession_key":row["accession_key_sha256"] = "f" * 64
    else:row["source_record_ordinal"] = True
    body["prefix_sha256"] = _sha(_raw(body["prefix"]))
    with pytest.raises(module.EarlyParentCaptureError):_selection(body)


def test_selection_weak_byte_seal_rejects_constructor_replace_or_mutation():
    selected = _selection()
    for changed in (module.InventedEarlySelection(selected.canonical_bytes(), object()), replace(selected)):
        with pytest.raises(module.EarlyParentCaptureError, match="genuine_unchanged_selection"):
            changed.to_payload()


def test_capture_no_resuming_existing_root(tmp_path):
    _run(tmp_path, response=module.SecHttpResult(403, (), b""))
    with pytest.raises(module.EarlyParentCaptureError, match="permanent_claim_or_capture_already_exists"):
        _run(tmp_path)


def test_response_framing_remains_real_no_synthetic_content_length(tmp_path):
    selection = _selection();by_url = {i["request"]["url"]: i["request"] for i in selection.to_payload()["requests"]}
    def response(url, _):
        return module.SecHttpResult(200, (("Transfer-Encoding", "chunked"),), _body(by_url[url]))
    result = _run(tmp_path, selection=selection, response=response)
    run = _namespace(tmp_path) / "runs" / result["capture_id"]
    child = json.loads((run / "request-000-result.json").read_bytes())
    assert child["observed_framing_headers"] == [["Transfer-Encoding", "chunked"]]
    module.verify_invented_capture(result["capture_id"], root=tmp_path, expected_report_sha256=result["report_sha256"])


@pytest.mark.parametrize("alias", ["literal", "symlink", "case", "ancestor-case"])
def test_fixture_real_lane_inode_alias_refuses_before_any_callback(tmp_path, monkeypatch, alias):
    if alias == "literal":
        root = LANE
    elif alias == "symlink":
        root = tmp_path / "lane-link"
        root.symlink_to(LANE, target_is_directory=True)
    elif alias == "case":
        root = LANE.with_name(LANE.name.upper())
        if not root.exists() or not root.samefile(LANE):
            pytest.skip("volume has no case alias")
    else:
        root = LANE.parent.with_name(LANE.parent.name.upper())
        if not root.exists() or not root.samefile(LANE.parent):
            pytest.skip("volume has no ancestor case alias")
    touched = []
    def forbidden(*args, **kwargs):
        touched.append(True)
        raise AssertionError("fixture reached callback or filesystem constructor")
    monkeypatch.setattr(module.bootstrap.custody, "_effective_denial", forbidden)
    monkeypatch.setattr(module.custody, "_Directory", forbidden)
    with pytest.raises(module.EarlyParentCaptureError, match="fixture_root_transport_required"):
        module.run_invented_capture(_selection(), "ib-sec-2006q1-initial64-invented", root=root,
            transport=forbidden, prior_open=forbidden)
    assert touched == []


def test_worker_cli_emits_canonical_result_for_its_strict_parent_decoder(monkeypatch, capsys):
    invented = {"fixture_only": True, "counts": {"started_requests": 2}, "report_sha256": "a" * 64}
    monkeypatch.setattr(module, "_verify_worker", lambda args: invented)
    assert module.main(["--verify-worker", "--capture-id", "ib-sec-2006q1-initial64-invented",
        "--expected-head", "a" * 40]) == 0
    assert module._json(capsys.readouterr().out.encode().rstrip(b"\n")) == invented


@pytest.mark.parametrize("tamper", ["boolean-status", "unknown-disposition", "context-count"])
def test_rehashed_terminal_controls_still_bind_policy_and_context(tmp_path, tamper):
    captured = _run(tmp_path, response=module.SecHttpResult(403, (), b""))
    run = _namespace(tmp_path) / "runs" / captured["capture_id"]
    report = json.loads((run / "complete.json").read_bytes())
    if tamper == "context-count":
        report["context_filings_not_requested"] += 1
    else:
        result_path = run / "request-000-result.json"
        result = json.loads(result_path.read_bytes())
        result["status" if tamper == "boolean-status" else "disposition"] = (
            True if tamper == "boolean-status" else "unrecognized-terminal-policy")
        result_raw = _raw(result);result_path.write_bytes(result_raw)
        report["results"][0]["result_sha256"] = _sha(result_raw)
    report_raw = _raw(report);(run / "complete.json").write_bytes(report_raw)
    with pytest.raises(module.EarlyParentCaptureError, match="terminal|context"):
        module.verify_invented_capture(captured["capture_id"], root=tmp_path,
            expected_report_sha256=_sha(report_raw))


@pytest.mark.parametrize("tamper", ["object", "claim", "start", "result", "extra_leaf", "nonprivate"])
def test_offline_verifier_refuses_changed_private_custody(tmp_path, tamper):
    result = _run(tmp_path, response=module.SecHttpResult(403, (), b""))
    run = _namespace(tmp_path) / "runs" / result["capture_id"]
    if tamper == "object":
        (run / "objects/extra.bin").write_bytes(b"invented");(run / "objects/extra.bin").chmod(0o600)
    elif tamper == "claim":
        next((_namespace(tmp_path) / "claims").iterdir()).write_bytes(b"{}")
    elif tamper == "extra_leaf":
        (run / "extra.json").write_bytes(b"{}");(run / "extra.json").chmod(0o600)
    elif tamper == "nonprivate":
        (run / "complete.json").chmod(0o644)
    else:
        (run / ("request-000-" + tamper + ".json")).write_bytes(b"{}")
    with pytest.raises((module.EarlyParentCaptureError, module.custody.FreshV4CaptureError)):
        module.verify_invented_capture(result["capture_id"], root=tmp_path, expected_report_sha256=result["report_sha256"])


def test_post_transport_source_change_refuses_before_body_or_result_publication(tmp_path):
    selection = _selection();changed = False;calls = []
    def guard():
        if changed:
            raise module.EarlyParentCaptureError("invented_source_changed")
    def wire(url, headers, cap):
        nonlocal changed
        calls.append(url);changed = True
        request = selection.to_payload()["requests"][0]["request"]
        raw = _body(request)
        return module.SecHttpResult(200, (("Content-Length", str(len(raw))),), raw)
    with pytest.raises(module.EarlyParentCaptureError, match="invented_source_changed"):
        _run(tmp_path, selection=selection, transport=wire, guard=guard)
    run = _namespace(tmp_path) / "runs/ib-sec-2006q1-initial64-invented"
    assert len(calls) == 1 and len(list((_namespace(tmp_path) / "claims").iterdir())) == 1
    assert (run / "request-000-start.json").is_file()
    assert not list((run / "objects").iterdir())
    assert not (run / "request-000-result.json").exists()
    assert not (run / "complete.json").exists()


def test_claim_without_start_is_permanently_consumed_after_clock_refusal(tmp_path):
    calls = []
    selection = _selection()
    with pytest.raises(module.EarlyParentCaptureError, match="completion_spacing_refused"):
        module.run_invented_capture(selection, "ib-sec-2006q1-initial64-invented", root=tmp_path,
            transport=_wire(selection, calls=calls), prior_open=_prior(selection),
            monotonic_ns=lambda: True, free_bytes=lambda: module.MIN_FREE_BYTES + 64 * module.MAX_PARENT_BYTES)
    assert calls == []
    assert len(list((_namespace(tmp_path) / "claims").iterdir())) == 1
    with pytest.raises(module.EarlyParentCaptureError, match="permanent_claim_or_capture_already_exists"):
        _run(tmp_path, capture_id="ib-sec-2006q1-initial64-second", calls=calls)
    assert calls == []


def test_identifying_contact_loaded_only_after_durable_reservation_before_first_claim(tmp_path):
    seen = []
    def contact():
        namespace = _namespace(tmp_path)
        run = namespace / "runs/ib-sec-2006q1-initial64-invented"
        reservation = json.loads((run / "reservation.json").read_bytes())
        assert reservation["contact_present"] is False
        assert list((namespace / "claims").iterdir()) == []
        assert not (run / "request-000-start.json").exists()
        seen.append("loaded")
        return "invented@unit.test"
    result = _run(tmp_path, contact=contact, response=module.SecHttpResult(403, (), b""))
    assert seen == ["loaded"]
    run = _namespace(tmp_path) / "runs" / result["capture_id"]
    validation = json.loads((run / "contact-validated.json").read_bytes())
    assert validation["contact_present"] is True and validation["contact_value_stored_or_hashed"] is False
    assert b"invented@unit.test" not in (run / "contact-validated.json").read_bytes()


def test_missing_contact_after_reservation_consumes_no_requests_or_claims(tmp_path):
    with pytest.raises(module.custody.FreshV4CaptureError, match="runtime SEC contact is invalid"):
        _run(tmp_path, contact=lambda: "", transport=lambda *_: pytest.fail("must not dispatch"))
    namespace = _namespace(tmp_path)
    assert list((namespace / "claims").iterdir()) == []
    run = namespace / "runs/ib-sec-2006q1-initial64-invented"
    assert (run / "reservation.json").exists()
    assert not (run / "contact-validated.json").exists()


def test_private_stdin_contact_is_bounded_and_not_echoed_or_logged(monkeypatch, capsys):
    monkeypatch.setattr(module.sys, "stdin", io.StringIO("invented@unit.test\n"))
    assert module._stdin_contact() == "invented@unit.test"
    assert capsys.readouterr().out == ""
    for raw in ("missing-newline", "a" * 256 + "\n"):
        monkeypatch.setattr(module.sys, "stdin", io.StringIO(raw))
        with pytest.raises(module.EarlyParentCaptureError, match="bounded_private_contact_input"):
            module._stdin_contact()


def test_draft_cli_cannot_activate_real_capture_or_verifier(capsys):
    code = module.main(["--verify-only", "--capture-id", "ib-sec-2006q1-initial64-invented",
        "--expected-head", "a" * 40, "--expected-report-sha256", "b" * 64])
    assert code == 2
    assert "refused_existing_claims_preserved" in capsys.readouterr().out


def test_explicit_stdin_cli_disables_echo_before_preflight_without_reading_contact(monkeypatch, capsys):
    events = []
    class InventedTTY:
        def isatty(self):return True
        def fileno(self):return 19
        def readline(self, _):pytest.fail("contact must not be read before durable reservation")
    original = [0, 0, 0, module.termios.ECHO | 1024, 0, 0, []]
    monkeypatch.setattr(module.sys, "stdin", InventedTTY())
    monkeypatch.setattr(module.termios, "tcgetattr", lambda fd: (events.append(("read-mode", fd)) or original))
    monkeypatch.setattr(module.termios, "tcsetattr", lambda fd, when, mode: events.append(("set-mode", fd, mode[3])))
    def refusal(*args, **kwargs):
        assert events[-1] == ("set-mode", 19, 1024)
        events.append(("preflight",))
        raise module.EarlyParentCaptureError("invented_source_refused")
    monkeypatch.setattr(module, "build_observed_selection", refusal)
    code = module.main(["--capture", "--read-contact-from-stdin", "--capture-id", "ib-sec-2006q1-initial64-invented",
        "--expected-head", "a" * 40])
    assert code == 2
    assert events[-1] == ("set-mode", 19, original[3])
    assert capsys.readouterr().out.count("refused_existing_claims_preserved") == 1


@pytest.mark.parametrize("where,expected_phase", [
    ("post-reservation-check", "post_reservation_check"),
    ("private-contact", "private_contact_validation"),
])
def test_cli_precontact_diagnostics_are_fixed_and_preserve_unclaimed_reservation(
        tmp_path, monkeypatch, capsys, where, expected_phase):
    secret = "PRIVATE-CONTACT=do-not-retain@invented.invalid /private/invented-secret"
    calls, contact_calls, guard_calls = [], [], []
    selected = _selection()
    def forbidden(*args, **kwargs):
        pytest.fail("diagnostic probe reached real transport")
    monkeypatch.setattr("http.client.HTTPSConnection", forbidden)
    def fail():
        raise OSError(errno.EACCES, secret, secret)
    def guard():
        guard_calls.append(True)
        if where == "post-reservation-check" and len(guard_calls) == 2:
            fail()
    def contact():
        contact_calls.append(True)
        if where == "private-contact":
            fail()
        return "invented@unit.test"
    monkeypatch.setattr(module, "build_observed_selection", lambda *args, **kwargs: selected)
    monkeypatch.setattr(module, "run_observed_capture", lambda *args, **kwargs:
        _run(tmp_path, selection=selected, guard=guard, contact=contact, calls=calls))
    assert module.main(["--capture", "--getpass-contact",
        "--capture-id", "ib-sec-2006q1-initial64-invented", "--expected-head", "a" * 40]) == 2
    output = capsys.readouterr().out
    result = json.loads(output)
    assert result == {"disposition": "early_parent_capture_or_verifier_refused_existing_claims_preserved",
                      "failure_phase": expected_phase, "failure_class": "OSError", "os_errno": errno.EACCES}
    assert secret not in output and "do-not-retain" not in output and "/private" not in output
    namespace = _namespace(tmp_path)
    run = namespace / "runs/ib-sec-2006q1-initial64-invented"
    assert (run / "reservation.json").exists()
    assert set(path.name for path in run.iterdir()) == {"reservation.json", "objects"}
    assert list((namespace / "claims").iterdir()) == [] and list((run / "objects").iterdir()) == []
    assert calls == [] and len(contact_calls) == (where == "private-contact")


@pytest.mark.parametrize("mode,expected_phase", [("--capture", "preflight"),
    ("--verify-only", "verifier"), ("--verify-worker", "verifier_worker")])
def test_cli_diagnostic_fallback_rejects_arbitrary_exception_fields(monkeypatch, capsys, mode, expected_phase):
    secret = "private arbitrary payload, path, contact and hash"
    class SecretSubclass(ValueError):
        pass
    failure = SecretSubclass(secret)
    failure._early_capture_failure_phase = secret
    failure.errno = secret
    def refusal(*args, **kwargs):
        raise failure
    monkeypatch.setattr(module, "build_observed_selection", refusal)
    monkeypatch.setattr(module, "verify_observed_capture", refusal)
    monkeypatch.setattr(module, "_verify_worker", refusal)
    assert module.main([mode, "--getpass-contact", "--capture-id", "ib-sec-2006q1-initial64-invented",
        "--expected-head", "a" * 40, "--expected-report-sha256", "b" * 64]) == 2
    output = capsys.readouterr().out
    assert json.loads(output) == {"disposition": "early_parent_capture_or_verifier_refused_existing_claims_preserved",
        "failure_phase": expected_phase, "failure_class": "ValueError", "os_errno": None}
    assert secret not in output and "SecretSubclass" not in output


@pytest.mark.parametrize("root", [LANE.parent, LANE / "artifacts/invented-fixture",
    Path("/Users/sheltonchen/Documents/Codex/2026-09-03/f/insider-source-20260929.hP4utF/selected-parents-v1")])
def test_fixture_fence_rejects_real_root_ancestor_descendant_and_known_sec_root(root):
    with pytest.raises(module.EarlyParentCaptureError, match="fixture_root_transport_required"):
        module.run_invented_capture(_selection(), "ib-sec-2006q1-initial64-invented", root=root,
            transport=lambda *_: pytest.fail("not reached"), prior_open=lambda: {})


# Section 194 (Claude review): the completion-spacing guard had no isolating test;
# the shared _Ticks clock always advanced by exactly the minimum interval.
class _OneNanosecondClock:
    """Advances one nanosecond per read; only the injected sleep moves it further."""
    def __init__(self):
        self.value = 0

    def __call__(self):
        self.value += 1
        return self.value


def _spacing_run(tmp_path, *, calls, monotonic_ns, sleep):
    selection = _selection()
    return module.run_invented_capture(selection, "ib-sec-2006q1-initial64-invented", root=tmp_path,
        transport=_wire(selection, calls=calls), prior_open=_prior(selection), clock=lambda: "2026-10-14T00:00:00Z",
        monotonic_ns=monotonic_ns, sleep=sleep, free_bytes=lambda: module.MIN_FREE_BYTES + 64 * module.MAX_PARENT_BYTES)


def test_completion_spacing_sleeps_the_remaining_interval_in_seconds(tmp_path):
    clock, slept, calls = _OneNanosecondClock(), [], []
    def sleep(seconds):
        slept.append(seconds)
        clock.value += round(seconds * 1_000_000_000)
    _spacing_run(tmp_path, calls=calls, monotonic_ns=clock, sleep=sleep)
    interval = module.MIN_COMPLETION_INTERVAL_NS / 1_000_000_000
    assert len(calls) == module.MAX_REQUESTS and len(slept) == module.MAX_REQUESTS - 1
    assert all(interval - 1e-6 < seconds < interval for seconds in slept)


def test_a_sleep_that_does_not_restore_spacing_refuses_before_the_second_start(tmp_path):
    calls = []
    with pytest.raises(module.EarlyParentCaptureError, match="completion_spacing_refused"):
        _spacing_run(tmp_path, calls=calls, monotonic_ns=_OneNanosecondClock(), sleep=lambda _: None)
    run = _namespace(tmp_path) / "runs/ib-sec-2006q1-initial64-invented"
    assert len(calls) == 1
    assert len(list((_namespace(tmp_path) / "claims").iterdir())) == 2
    assert (run / "request-000-result.json").is_file()
    assert not (run / "request-001-start.json").exists()
    assert not (run / "complete.json").exists()


# Section 194 (Claude review): the observed-mode fixed root/transport clause had no
# isolating test. The type-shaped selection below is deliberately UNSEALED, so even a
# missing clause refuses before payload, contact, journal or network access.
@pytest.mark.parametrize("invalid", ["root", "transport"])
def test_observed_capture_requires_the_fixed_lane_root_and_real_transport(tmp_path, monkeypatch, invalid):
    monkeypatch.setattr("http.client.HTTPSConnection", lambda *a, **k: pytest.fail("No connection"))
    chosen = module.ObservedEarlySelection(b"", object())
    root = tmp_path.resolve() if invalid == "root" else module.bootstrap.custody.LANE_ROOT
    transport = module._selected_sec_transport if invalid == "root" else (lambda *a, **k: pytest.fail("No dispatch"))
    with pytest.raises(module.EarlyParentCaptureError, match="actual_fixed_root_transport_required"):
        module._capture(chosen, "ib-sec-2006q1-initial64-invented", lambda: pytest.fail("No contact"),
            root=root, observed=True, transport=transport, guard=lambda: pytest.fail("No guard"),
            prior_open=lambda: pytest.fail("No prior roots"))
    assert not _namespace(tmp_path).exists()


# Section 194 (Claude review): a local body-retention failure escapes; it is never
# recorded as a source-side refusal of an HTTP-200 response.
def test_local_retention_failure_escapes_instead_of_recording_a_source_refusal(tmp_path, monkeypatch):
    import errno as _errno
    publish = module.custody._Directory.publish
    def failing(self, name, raw, **kwargs):
        if name.endswith(".bin"):
            raise OSError(_errno.ENOSPC, "invented disk full")
        return publish(self, name, raw, **kwargs)
    monkeypatch.setattr(module.custody._Directory, "publish", failing)
    calls = []
    with pytest.raises(OSError):
        _run(tmp_path, calls=calls)
    run = _namespace(tmp_path) / "runs/ib-sec-2006q1-initial64-invented"
    assert len(calls) == 1 and (run / "request-000-start.json").is_file()
    assert not (run / "request-000-result.json").exists()
    assert not (run / "complete.json").exists()
