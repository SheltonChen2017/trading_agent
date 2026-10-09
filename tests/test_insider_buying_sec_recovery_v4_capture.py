"""Invented requests/parents and injected transport only; OS network denial."""
import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest

from research import insider_buying_sec_recovery_v4_capture as m
from research import insider_buying_sec_recovery_v4_selection as selection
from research.insider_buying_sec_complete_acquisition import SecHttpResult


CONTACT = "invented-private-contact@unit.test"


def request(number=1, **changes):
    accession = f"0000000001-23-{number:06d}"
    value = {"period": "2023Q1", "accession_number": accession, "form_type": "4", "filing_date": "2023-01-03",
        "issuer_cik": "0000000001", "archive_path": f"edgar/data/1/{accession}.txt",
        "submission_row_id": f"{number:064x}", "parsed_lineage_hash": "b" * 64,
        "master_source_sha256": "a" * 64, "url": f"https://www.sec.gov/Archives/edgar/data/1/{accession}.txt"}
    value.update(changes)
    return value


def parent(item):
    accession, filed = item["accession_number"], item["filing_date"].replace("-", "")
    return (f"<SEC-DOCUMENT>{accession}.txt : {filed}\n"
        f"<SEC-HEADER>{accession}.hdr.sgml : {filed}\n<ACCEPTANCE-DATETIME>{filed}101112\n"
        f"<ACCESSION-NUMBER>{accession}\n<TYPE>{item['form_type']}\n<FILING-DATE>{filed}\n"
        "<REPORTING-OWNER>\n<OWNER-DATA>\n<CIK>0000000002\n<CONFORMED-NAME>Invented Owner\n"
        "</OWNER-DATA>\n</REPORTING-OWNER>\n<ISSUER>\n<COMPANY-DATA>\n"
        f"<CIK>{item['issuer_cik'].zfill(10)}\n</COMPANY-DATA>\n</ISSUER>\n</SEC-HEADER>\n"
        "<DOCUMENT>\n<TYPE>4\n<SEQUENCE>1\n<FILENAME>invented.xml\n<TEXT>\ninvented\n"
        "</TEXT>\n</DOCUMENT>\n</SEC-DOCUMENT>\n").encode()


class Clock:
    def __init__(self): self.ns, self.sleeps = 0, []
    def monotonic(self): return self.ns
    def sleep(self, seconds): self.sleeps.append(seconds); self.ns += round(seconds * 1e9)
    def stamp(self): return "2026-10-07T12:00:00.000000+00:00"


def directories(root, capture_id="fixture-first"):
    base = root.resolve().joinpath(*m.ARTIFACT_PARTS)
    return base, base / "claims", base / "runs" / capture_id


def run(tmp_path, *, items=None, capture_id="fixture-first", supplied=None, transport=None, **options):
    items = (request(),) if items is None else items
    chosen = selection.make_invented_test_selection(tuple(items))
    clock, calls = Clock(), []
    _, claims, output = directories(tmp_path, capture_id)
    def injected(url, headers, cap):
        calls.append((url, clock.ns))
        assert cap == m.MAX_PARENT_BYTES
        assert headers == {"User-Agent": f"InsiderBuyingResearch-v4-first64/1.0 ({CONTACT})",
            "Accept": "*/*", "Accept-Encoding": "identity", "Connection": "close"}
        reservation = json.loads((output / "reservation.json").read_bytes())
        assert reservation["contact_present"] is True and reservation["maximum_attempts_per_request"] == 1
        assert len(list(claims.iterdir())) == len(items)
        ordinal = len(calls) - 1
        assert (output / f"request-{ordinal:03d}-start.json").is_file()
        clock.ns += 100_000_000
        if supplied is not None: return supplied
        raw = parent(items[ordinal])
        return SecHttpResult(200, (("Content-Length", str(len(raw))),), raw)
    result = m._run_invented_capture(chosen, capture_id, root=tmp_path.resolve(),
        transport=injected if transport is None else transport, contact_email=CONTACT,
        clock=clock.stamp, monotonic_ns=clock.monotonic, sleep=clock.sleep, **options)
    return result, calls, clock, chosen


def test_success_all_claims_and_starts_before_http_exact_count_and_contact_absent(tmp_path):
    items = (request(1), request(2), request(3))
    result, calls, clock, chosen = run(tmp_path, items=items)
    assert result["scope"] == "invented_test_only" and result["batch_completed"] is True
    assert result["sec_dispatches"] == result["completed_request_bound_bodies"] == 3
    assert [instant for _, instant in calls] == [0, 600_000_000, 1_200_000_000]
    assert clock.sleeps == [0.5, 0.5]
    assert result["selection_sha256"] == chosen.sha256
    assert result["authority"]["bounded_named_source_acquisition_scope"] is False
    assert all(value is False for key, value in result["authority"].items() if type(value) is bool)
    base, claims, output = directories(tmp_path)
    assert len(list(claims.iterdir())) == 3
    assert len(list((output / "objects").iterdir())) == 3
    assert m._sha((output / "complete.json").read_bytes()) == result["report_sha256"]
    for leaf in base.rglob("*"):
        if leaf.is_file():
            assert stat.S_IMODE(leaf.stat().st_mode) == 0o600 and leaf.stat().st_nlink == 1
            assert CONTACT.encode() not in leaf.read_bytes()
        else: assert stat.S_IMODE(leaf.stat().st_mode) == 0o700


def test_64_distinct_original_identities_are_finite_without_small_cap_bypass(tmp_path):
    result, calls, _, _ = run(tmp_path, items=tuple(request(i) for i in range(1, 65)))
    assert result["sec_dispatches"] == result["completed_request_bound_bodies"] == len(calls) == 64
    assert result["batch_completed"] is True


@pytest.mark.parametrize("status", [301, 302, 400, 401, 403, 429, 500, 502, 503, 504])
def test_any_non200_halts_once_no_retry_or_fallback(tmp_path, status):
    result, calls, _, _ = run(tmp_path, items=(request(1), request(2)), supplied=SecHttpResult(status, (), b""))
    assert len(calls) == result["sec_dispatches"] == 1
    assert result["completed_request_bound_bodies"] == 0 and not result["batch_completed"]
    _, claims, output = directories(tmp_path)
    assert len(list(claims.iterdir())) == 2
    report = json.loads((output / "complete.json").read_bytes())
    assert report["reserved_not_attempted"] == 1 and report["retained_body_bytes"] == 0
    attempt = json.loads((output / "request-000-result.json").read_bytes())
    assert attempt["disposition"] == "http-refused-no-retry" and attempt["status"] == status
    assert list((output / "objects").iterdir()) == []


@pytest.mark.parametrize("malformed", [None, {}, SecHttpResult(True, (), b""), SecHttpResult(200, (), b"bad"),
    SecHttpResult(200, (("Content-Length", "3"),), bytearray(b"bad")),
    SecHttpResult(200, (("Content-Length", "999"),), b"bad"),
    SecHttpResult(200, (("Content-Length", "3"), ("Content-Length", "3")), b"bad"),
    SecHttpResult(200, (("Content-Encoding", "gzip"), ("Content-Length", "3")), b"bad")])
def test_bad_response_shape_framing_or_parent_halts_without_raw_persistence(tmp_path, malformed):
    result, calls, _, _ = run(tmp_path, items=(request(1), request(2)), transport=lambda *args: malformed)
    assert result["sec_dispatches"] == 1 and result["completed_request_bound_bodies"] == 0
    _, claims, output = directories(tmp_path)
    assert len(list(claims.iterdir())) == 2 and not list((output / "objects").iterdir())
    assert (output / "request-000-start.json").is_file()


@pytest.mark.parametrize("change", ["issuer", "accession", "form", "filing"])
def test_body_bound_to_exact_request_not_only_http200(tmp_path, change):
    raw = parent(request())
    if change == "issuer": raw = raw.replace(b"<CIK>0000000001", b"<CIK>0000000099")
    if change == "accession": raw = raw.replace(b"0000000001-23-000001", b"0000000001-23-000009")
    if change == "form": raw = raw.replace(b"<TYPE>4", b"<TYPE>5")
    if change == "filing": raw = raw.replace(b"<FILING-DATE>20230103", b"<FILING-DATE>20230104")
    result, _, _, _ = run(tmp_path, supplied=SecHttpResult(200, (("Content-Length", str(len(raw))),), raw))
    assert result["completed_request_bound_bodies"] == 0
    assert not list(directories(tmp_path)[2].joinpath("objects").iterdir())


def test_ambiguous_transport_exception_consumes_claim_and_cannot_new_id_redispatch(tmp_path):
    calls = []
    def failure(*args): calls.append(1); raise TimeoutError(CONTACT)
    first, _, _, chosen = run(tmp_path, transport=failure)
    assert first["sec_dispatches"] == len(calls) == 1 and first["completed_request_bound_bodies"] == 0
    with pytest.raises(m.FreshV4CaptureError, match="already reserved"):
        m._run_invented_capture(chosen, "another-capture", root=tmp_path.resolve(),
            transport=lambda *args: pytest.fail("Ambiguous request must not redispatch"), contact_email=CONTACT)
    assert CONTACT not in json.dumps(first)
    assert "Timeout" not in directories(tmp_path)[2].joinpath("request-000-result.json").read_text()


def test_changed_lineage_and_locator_alias_cannot_bypass_accession_claim(tmp_path):
    _, _, _, _ = run(tmp_path)
    changed = request(parsed_lineage_hash="c" * 64, archive_path="edgar/data/99/0000000001-23-000001.txt",
                      url="https://www.sec.gov/Archives/edgar/data/99/0000000001-23-000001.txt")
    chosen = selection.make_invented_test_selection((changed,))
    with pytest.raises(m.FreshV4CaptureError, match="already reserved"):
        m._run_invented_capture(chosen, "different-lineage", root=tmp_path.resolve(),
            transport=lambda *args: pytest.fail("Accession must not duplicate"))


def test_known_duplicate_late_in_prefix_refuses_before_any_new_claim_or_http(tmp_path):
    run(tmp_path, items=(request(2),))
    _, claims, _ = directories(tmp_path)
    before = {p.name for p in claims.iterdir()}
    chosen = selection.make_invented_test_selection((request(1), request(2)))
    with pytest.raises(m.FreshV4CaptureError, match="already reserved"):
        m._run_invented_capture(chosen, "new-prefix", root=tmp_path.resolve(), transport=lambda *args: pytest.fail("No partial dispatch"))
    assert {p.name for p in claims.iterdir()} == before
    assert not directories(tmp_path, "new-prefix")[2].exists()


def test_crash_after_start_preserves_pending_start_no_resume_even_same_or_new_id(tmp_path):
    def crash(*args): raise SystemExit("invented crash")
    with pytest.raises(SystemExit): run(tmp_path, transport=crash)
    _, claims, output = directories(tmp_path)
    assert len(list(claims.iterdir())) == 1 and (output / "request-000-start.json").exists()
    assert not (output / "request-000-result.json").exists() and not (output / "complete.json").exists()
    chosen = selection.make_invented_test_selection((request(),))
    with pytest.raises(m.FreshV4CaptureError, match="already exists"):
        m._run_invented_capture(chosen, "fixture-first", root=tmp_path.resolve(), transport=lambda *args: pytest.fail("No resume"))
    with pytest.raises(m.FreshV4CaptureError, match="already reserved"):
        m._run_invented_capture(chosen, "after-crash", root=tmp_path.resolve(), transport=lambda *args: pytest.fail("No duplicate"))


def test_initial_identity_refusal_precedes_journal_or_transport(tmp_path):
    def guard(): raise m.FreshV4CaptureError("REFUSED: invented lane drift")
    with pytest.raises(m.FreshV4CaptureError, match="lane drift"):
        run(tmp_path, guard=guard, transport=lambda *args: pytest.fail("No request"))
    assert not directories(tmp_path)[0].exists()


def test_identity_refusal_after_fsynced_start_consumes_claim_before_http(tmp_path):
    calls = []
    def guard():
        calls.append(1)
        if len(calls) == 3: raise m.FreshV4CaptureError("REFUSED: invented post-start lane drift")
    with pytest.raises(m.FreshV4CaptureError, match="post-start"):
        run(tmp_path, guard=guard, transport=lambda *args: pytest.fail("No request"))
    _, claims, output = directories(tmp_path)
    assert len(list(claims.iterdir())) == 1 and (output / "request-000-start.json").exists()


def test_insufficient_free_capacity_refuses_before_reservation_and_claims(tmp_path):
    with pytest.raises(m.FreshV4CaptureError, match="capacity"):
        run(tmp_path, free_bytes=lambda: m.MIN_FREE_BYTES + m.MAX_PARENT_BYTES - 1)
    _, claims, output = directories(tmp_path)
    assert not list(claims.iterdir()) and not output.exists()


def test_sleep_that_does_not_enforce_completion_spacing_stops_second_request(tmp_path):
    chosen = selection.make_invented_test_selection((request(1), request(2)))
    calls, timer = [], Clock()
    def transport(url, *args):
        calls.append(url); raw = parent(request(len(calls)))
        return SecHttpResult(200, (("Content-Length", str(len(raw))),), raw)
    with pytest.raises(m.FreshV4CaptureError, match="spacing"):
        m._run_invented_capture(chosen, "fixture-first", root=tmp_path.resolve(), transport=transport,
            monotonic_ns=timer.monotonic, sleep=lambda _: None)
    assert len(calls) == 1


@pytest.mark.parametrize("contact", ["", "not-an-email", "a\r\n@host.com", "a@bad..com", "a@-bad.com", "a@host", "a@host.c", True])
def test_bad_contact_refuses_before_any_journal(tmp_path, contact):
    chosen = selection.make_invented_test_selection((request(),))
    with pytest.raises(m.FreshV4CaptureError, match="contact"):
        m._run_invented_capture(chosen, "fixture-first", root=tmp_path.resolve(), contact_email=contact,
            transport=lambda *args: pytest.fail("No request"))
    assert not directories(tmp_path)[0].exists()


@pytest.mark.parametrize("contact", ["a@example.com", "a@unit.test", "a@unit.invalid", "a@unit.example"])
def test_reserved_placeholder_contact_cannot_enter_real_scope(contact):
    with pytest.raises(m.FreshV4CaptureError, match="contact"): m._contact(contact, observed=True)


@pytest.mark.parametrize("encoded", [CONTACT, CONTACT.replace("@", "&#64;"), CONTACT.replace("@", "%40"),
    "\\u0069" + CONTACT[1:], "\\x69" + CONTACT[1:], "\\U00000069" + CONTACT[1:],
    CONTACT.replace("@", "%2540"), CONTACT.replace("@", "&amp;#64;"),
    CONTACT.replace("@", "%255Cu0040")])
def test_contact_echo_in_success_body_halts_without_persisting_contact(tmp_path, encoded):
    raw = parent(request()).replace(b"invented\n", encoded.encode() + b"\n")
    result, _, _, _ = run(tmp_path, supplied=SecHttpResult(200, (("Content-Length", str(len(raw))),), raw))
    assert result["completed_request_bound_bodies"] == 0
    for leaf in directories(tmp_path)[0].rglob("*"):
        if leaf.is_file(): assert CONTACT.encode() not in leaf.read_bytes()
    assert not list(directories(tmp_path)[2].joinpath("objects").iterdir())


def test_literal_percent_contact_echo_is_screened_before_decoding(tmp_path):
    contact = "invented%25private@unit.test"
    chosen = selection.make_invented_test_selection((request(),))
    raw = parent(request()).replace(b"invented\n", contact.encode() + b"\n")
    clock = Clock()
    result = m._run_invented_capture(chosen, "fixture-first", root=tmp_path.resolve(), contact_email=contact,
        transport=lambda *args: SecHttpResult(200, (("Content-Length", str(len(raw))),), raw),
        clock=clock.stamp, monotonic_ns=clock.monotonic, sleep=clock.sleep)
    assert result["completed_request_bound_bodies"] == 0
    assert not list(directories(tmp_path)[2].joinpath("objects").iterdir())


def test_contact_screen_refuses_unfinished_encoding_at_explicit_depth_bound(tmp_path):
    encoded_at = "%40"
    for _ in range(m.MAX_ECHO_DECODE_LAYERS + 1): encoded_at = encoded_at.replace("%", "%25")
    raw = parent(request()).replace(b"invented\n", CONTACT.replace("@", encoded_at).encode() + b"\n")
    result, calls, _, _ = run(tmp_path, items=(request(1), request(2)),
        supplied=SecHttpResult(200, (("Content-Length", str(len(raw))),), raw))
    assert result["completed_request_bound_bodies"] == 0 and len(calls) == 1
    assert not list(directories(tmp_path)[2].joinpath("objects").iterdir())


def test_contact_screen_is_only_a_view_and_accepts_unrelated_standard_escapes(tmp_path):
    raw = parent(request()).replace(b"invented\n", b"unrelated\\u0061&amp;%20body\n")
    result, _, _, _ = run(tmp_path, supplied=SecHttpResult(200, (("Content-Length", str(len(raw))),), raw))
    assert result["completed_request_bound_bodies"] == 1
    assert (directories(tmp_path)[2] / "objects" / (m._sha(raw) + ".bin")).read_bytes() == raw


def test_default_real_entry_rejects_invented_selection_before_contact_or_network():
    chosen = selection.make_invented_test_selection((request(),))
    with pytest.raises(m.FreshV4CaptureError, match="genuinely replayed"):
        m.run_observed_fresh_v4_capture(chosen, "fixture", expected_head="a" * 40, contact_email=CONTACT)


def test_symlink_claims_directory_cannot_bypass_global_namespace(tmp_path):
    base, claims, output = directories(tmp_path)
    base.mkdir(parents=True, mode=0o700)
    external = tmp_path / "alternate"; external.mkdir(mode=0o700)
    claims.symlink_to(external, target_is_directory=True)
    with pytest.raises((m.FreshV4CaptureError, OSError)):
        run(tmp_path, transport=lambda *args: pytest.fail("No request"))
    assert not output.exists() and not list(external.iterdir())


def test_fifo_lock_refused_without_blocking_or_transport(tmp_path):
    base, _, _ = directories(tmp_path)
    base.mkdir(parents=True, mode=0o700)
    os.mkfifo(base / "capture.lock", mode=0o600)
    with pytest.raises(m.FreshV4CaptureError, match="lock custody"):
        run(tmp_path, transport=lambda *args: pytest.fail("No request"))


def test_claim_tamper_after_first_transport_refuses_before_second(tmp_path):
    _, claims, _ = directories(tmp_path)
    calls = []
    def transport(url, *args):
        calls.append(url)
        leaf = next(claims.iterdir()); leaf.write_bytes(b"tampered\n")
        raw = parent(request())
        return SecHttpResult(200, (("Content-Length", str(len(raw))),), raw)
    with pytest.raises(m.FreshV4CaptureError, match="durable capture or claim"):
        run(tmp_path, items=(request(1), request(2)), transport=transport)
    assert len(calls) == 1


def test_global_claim_lock_other_owner_refuses_nonblocking_no_request(tmp_path):
    run(tmp_path)
    base, _, _ = directories(tmp_path)
    import fcntl
    fd = os.open(base / "capture.lock", os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        chosen = selection.make_invented_test_selection((request(2),))
        with pytest.raises(m.FreshV4CaptureError, match="global claims lock"):
            m._run_invented_capture(chosen, "other-lock", root=tmp_path.resolve(), transport=lambda *args: pytest.fail("No request"))
    finally: os.close(fd)


def test_final_report_named_bytes_rechecked_before_return(tmp_path, monkeypatch):
    original = m._Directory.publish
    def substitute(folder, name, raw, **kwargs):
        digest = original(folder, name, raw, **kwargs)
        if name == "complete.json": (folder.path / name).write_bytes(b"tampered-final-report\n")
        return digest
    monkeypatch.setattr(m._Directory, "publish", substitute)
    with pytest.raises(m.FreshV4CaptureError, match="durable capture or claim"):
        run(tmp_path)


def verify(tmp_path, result):
    return m._verify_capture(result["capture_id"], result["report_sha256"], root=tmp_path.resolve(), observed=False)


def test_independent_readonly_journal_replay_all_bytes_and_no_new_transport(tmp_path):
    result, calls, _, _ = run(tmp_path, items=(request(1), request(2)))
    before = {p: m._sha(p.read_bytes()) for p in directories(tmp_path)[0].rglob("*") if p.is_file()}
    replay = verify(tmp_path, result)
    assert replay["independent_readonly_journal_replay"] is True
    assert replay["sec_dispatches"] == replay["completed_request_bound_bodies"] == len(calls) == 2
    assert replay["report_sha256"] == result["report_sha256"] and replay["batch_completed"]
    after = {p: m._sha(p.read_bytes()) for p in directories(tmp_path)[0].rglob("*") if p.is_file()}
    assert before == after


def test_independent_failed_request_replay_retains_all_reserved_counts(tmp_path):
    result, _, _, _ = run(tmp_path, items=(request(1), request(2)), supplied=SecHttpResult(403, (), b""))
    replay = verify(tmp_path, result)
    assert replay["sec_dispatches"] == 1 and replay["completed_request_bound_bodies"] == 0
    assert replay["batch_completed"] is False


@pytest.mark.parametrize("leaf", ["complete.json", "reservation.json", "request-000-start.json", "request-000-result.json", "claim", "object"])
def test_independent_replay_detects_any_retained_leaf_tamper(tmp_path, leaf):
    result, _, _, _ = run(tmp_path)
    _, claims, output = directories(tmp_path)
    path = next(claims.iterdir()) if leaf == "claim" else next((output / "objects").iterdir()) if leaf == "object" else output / leaf
    path.write_bytes(b"tampered\n")
    with pytest.raises((m.FreshV4CaptureError, ValueError)): verify(tmp_path, result)


def test_independent_replay_rejects_complete_report_with_boolean_count_even_reanchored(tmp_path):
    result, _, _, _ = run(tmp_path)
    path = directories(tmp_path)[2] / "complete.json"
    report = json.loads(path.read_bytes()); report["sec_dispatches"] = True
    raw = m._canonical(report); path.write_bytes(raw)
    result["report_sha256"] = m._sha(raw)
    with pytest.raises(m.FreshV4CaptureError, match="denominator"): verify(tmp_path, result)


def test_independent_replay_rejects_unknown_leaf_not_silently_omits_it(tmp_path):
    result, _, _, _ = run(tmp_path)
    leaf = directories(tmp_path)[2] / "unknown.json"; leaf.write_bytes(b"{}\n"); leaf.chmod(0o600)
    with pytest.raises(m.FreshV4CaptureError, match="leaf inventory"): verify(tmp_path, result)


def test_independent_replay_checks_recomputed_monotonic_spacing_not_just_hashes(tmp_path):
    result, _, _, _ = run(tmp_path, items=(request(1), request(2)))
    output = directories(tmp_path)[2]
    start = json.loads((output / "request-001-start.json").read_bytes()); start["started_monotonic_ns"] = 100_000_001
    start_raw = m._canonical(start); (output / "request-001-start.json").write_bytes(start_raw)
    attempt = json.loads((output / "request-001-result.json").read_bytes()); attempt["start_sha256"] = m._sha(start_raw)
    attempt_raw = m._canonical(attempt); (output / "request-001-result.json").write_bytes(attempt_raw)
    report = json.loads((output / "complete.json").read_bytes()); report["results"][1]["result_sha256"] = m._sha(attempt_raw)
    report_raw = m._canonical(report); (output / "complete.json").write_bytes(report_raw)
    result["report_sha256"] = m._sha(report_raw)
    with pytest.raises(m.FreshV4CaptureError, match="spacing"): verify(tmp_path, result)


def test_parent_persistence_failure_preserves_consumed_start_not_misreported_as_bad_source(tmp_path, monkeypatch):
    original = m._Directory.publish
    def fail(folder, name, raw, **kwargs):
        if name.endswith(".bin"): raise OSError("invented storage failure")
        return original(folder, name, raw, **kwargs)
    monkeypatch.setattr(m._Directory, "publish", fail)
    with pytest.raises(OSError): run(tmp_path)
    output = directories(tmp_path)[2]
    assert (output / "request-000-start.json").exists()
    assert not (output / "request-000-result.json").exists() and not (output / "complete.json").exists()


# Section 153 (Claude review): the observed-mode guard had no isolating control.
def test_observed_capture_refuses_an_invented_selection_before_any_journal(tmp_path):
    chosen = selection.make_invented_test_selection((request(),))
    with pytest.raises(m.FreshV4CaptureError, match="fixed genuine selection/transport/root"):
        m._capture(chosen, "fixture-first", chosen.to_payload()["repository_head"], CONTACT, root=tmp_path.resolve(),
                   transport=lambda *args: pytest.fail("No request"), guard=lambda: None, observed=True)
    base, _, _ = directories(tmp_path)
    assert not base.exists()


# Section 154: isolate each admission clause. The type-shaped object below is
# deliberately UNSEALED, not an observed selection or genuine replay proof.
# A second sentinel refuses before even contact/payload validation if a clause
# disappears. No real lane directory, journal or network can be reached.
@pytest.mark.parametrize("invalid_member", ("selection", "transport", "root"))
def test_observed_capture_each_admission_clause_refuses_before_contact(monkeypatch, tmp_path, invalid_member):
    from research.insider_buying_sec_selected_parent_runner import _selected_sec_transport

    monkeypatch.setattr("http.client.HTTPSConnection", lambda *a, **k: pytest.fail("No connection"))
    real_transport = _selected_sec_transport
    chosen = selection.FreshV4Selection(b"", object(), b"")
    root, transport = selection._base().LANE_ROOT, real_transport
    if invalid_member == "selection":
        chosen = selection.make_invented_test_selection((request(),))
    elif invalid_member == "transport":
        transport = lambda *a, **k: pytest.fail("No dispatch")
    else:
        root = tmp_path.resolve()
    monkeypatch.setattr(m, "_contact", lambda *a, **k: pytest.fail("Admission must refuse before contact"))
    monkeypatch.setattr(m, "_Directory", lambda *a, **k: pytest.fail("No journal access"))
    with pytest.raises(m.FreshV4CaptureError, match="fixed genuine selection/transport/root"):
        m._capture(chosen, "fixture-first", "a" * 40, CONTACT, root=root, transport=transport,
                   guard=lambda: pytest.fail("No repository guard"), observed=True)
    assert not directories(tmp_path)[0].exists()
