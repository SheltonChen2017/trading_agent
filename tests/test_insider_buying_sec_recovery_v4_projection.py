"""Invented capture journals and complete parents only; OS network denied."""
import copy
import gc
import json
from pathlib import Path
import subprocess
import sys
import weakref

import pytest

from research import insider_buying_sec_recovery_v4_capture as capture
from research import insider_buying_sec_recovery_v4_selection as selection
from research import insider_buying_sec_recovery_v4_projection as m
from research.insider_buying_sec_complete_acquisition import SecHttpResult


def request(number=1, form="4"):
    accession = f"0000000001-23-{number:06d}"
    return {"period": "2023Q1", "accession_number": accession, "form_type": form, "filing_date": "2023-01-03",
        "issuer_cik": "1", "archive_path": f"edgar/data/2/{accession}.txt",
        "submission_row_id": f"{number:064x}", "parsed_lineage_hash": "b" * 64,
        "master_source_sha256": "a" * 64, "url": f"https://www.sec.gov/Archives/edgar/data/2/{accession}.txt"}


def parent(item, *, xml=None, legacy=False):
    accession, form = item["accession_number"], item["form_type"]
    header = (f"<ACCEPTANCE-DATETIME>20230103101112\n<ACCESSION-NUMBER>{accession}\n"
        f"<TYPE>{form}\n<FILING-DATE>20230103\n<REPORTING-OWNER>\n<OWNER-DATA>\n"
        "<CIK>0000000002\n<CONFORMED-NAME>Invented Owner\n</OWNER-DATA>\n</REPORTING-OWNER>\n"
        "<ISSUER>\n<COMPANY-DATA>\n<CIK>0000000001\n</COMPANY-DATA>\n</ISSUER>\n")
    if legacy:
        header = (f"<ACCEPTANCE-DATETIME>20230103101112\nACCESSION NUMBER:\t{accession}\n"
            f"CONFORMED SUBMISSION TYPE:\t{form}\nPUBLIC DOCUMENT COUNT:\t1\n"
            "CONFORMED PERIOD OF REPORT:\t20230103\nFILED AS OF DATE:\t20230103\nDATE AS OF CHANGE:\t20230103\n\n"
            "REPORTING-OWNER:\n\n\tOWNER DATA:\n\t\tCOMPANY CONFORMED NAME:\tInvented Owner\n"
            f"\t\tCENTRAL INDEX KEY:\t0000000002\n\n\tFILING VALUES:\n\t\tFORM TYPE:\t{form}\n"
            "\n\tMAIL ADDRESS:\n\t\tSTREET 1:\tInvented Street\n\nISSUER:\n\n\tCOMPANY DATA:\n"
            "\t\tCOMPANY CONFORMED NAME:\tInvented Issuer\n\t\tCENTRAL INDEX KEY:\t0000000001\n"
            "\n\tBUSINESS ADDRESS:\n\t\tSTREET 1:\tInvented Road\n\n\tMAIL ADDRESS:\n\t\tSTREET 1:\tInvented Road\n")
    xml = (f'<ownershipDocument><documentType>{form}</documentType><issuer><issuerCik>0000000001</issuerCik></issuer>'
        '<reportingOwner><reportingOwnerId><rptOwnerCik>0000000002</rptOwnerCik></reportingOwnerId>'
        '</reportingOwner><nonDerivativeTable><nonDerivativeTransaction><transactionAmounts>'
        '<transactionShares><value>987654.321</value></transactionShares></transactionAmounts>'
        '</nonDerivativeTransaction></nonDerivativeTable></ownershipDocument>\n') if xml is None else xml
    return (f"<SEC-DOCUMENT>{accession}.txt : 20230103\n<SEC-HEADER>{accession}.hdr.sgml : 20230103\n"
        + header + f"</SEC-HEADER>\n<DOCUMENT>\n<TYPE>{form}\n<SEQUENCE>1\n<FILENAME>ownership.xml\n<TEXT>\n"
        + xml + "</TEXT>\n</DOCUMENT>\n</SEC-DOCUMENT>\n").encode()


class Clock:
    ns = 0
    def now(self): return self.ns
    def sleep(self, seconds): self.ns += round(seconds * 1e9)


def captured(tmp_path, *, items=None, bodies=None, failure=False):
    items = (request(),) if items is None else tuple(items)
    bodies = [parent(item) for item in items] if bodies is None else bodies
    chosen = selection.make_invented_test_selection(items)
    clock, calls = Clock(), []
    def transport(*args):
        ordinal = len(calls); calls.append(ordinal)
        if failure: return SecHttpResult(403, (), b"")
        raw = bodies[ordinal]
        return SecHttpResult(200, (("Content-Length", str(len(raw))),), raw)
    result = capture._run_invented_capture(chosen, "invented-projection", root=tmp_path.resolve(), transport=transport,
        contact_email="invented@unit.test", monotonic_ns=clock.now, sleep=clock.sleep,
        clock=lambda: "2026-10-07T12:00:00.000000+00:00")
    return result, items


def project(tmp_path, result):
    return m._project_root(result["capture_id"], result["report_sha256"], root=tmp_path.resolve(), observed=False,
        consumer=lambda: {"scope": "invented_test_only", "source_only_attested": False})


@pytest.mark.parametrize("form", ["4", "4/A"])
@pytest.mark.parametrize("legacy", [False, True])
def test_exact_target_header_xml_projection_noncanonical_and_compact(tmp_path, form, legacy):
    item = request(form=form); raw = parent(item, legacy=legacy)
    result, _ = captured(tmp_path, items=(item,), bodies=[raw])
    receipt = project(tmp_path, result); body = receipt.to_payload(); row = body["rows"][0]
    assert body["scope"] == "invented_test_only" and body["capture_git_commit"] == "a" * 40
    assert row["target"]["issuer_cik"] == "0000000001" and row["target"]["complete_submission_url"] == item["url"]
    assert row["target"]["quarterly_index_sha256"] == item["master_source_sha256"]
    assert row["projection"]["accepted_at_raw"] == "20230103101112"
    assert row["projection"]["header_owner_cik_count"] == 1
    assert row["raw_parent"] == {"sha256": capture._sha(raw), "size_bytes": len(raw)}
    assert body["counts"] == {"header_bound_retained": 1, "complete_parent_projected": 1,
        "complete_parent_grammar_quarantined": 0, "raw_parent_bytes": len(raw)}
    assert b"987654.321" not in receipt.raw_bytes and b"Invented Owner" not in receipt.raw_bytes
    assert b"ownershipDocument" not in receipt.raw_bytes and b"header_owner_ciks" not in receipt.raw_bytes
    assert all(value is False if type(value) is bool else value == 0 for value in body["authority"].values())
    assert body["denominator"]["source_bound_union_count_promoted"] is False
    assert receipt.sha256 == capture._sha(receipt.raw_bytes)


def test_unsupported_complete_grammar_is_named_not_zero_or_lost_capture(tmp_path):
    items = (request(1), request(2))
    result, _ = captured(tmp_path, items=items, bodies=[parent(items[0]), parent(items[1], xml="unsupported\n")])
    body = project(tmp_path, result).to_payload()
    assert body["counts"]["header_bound_retained"] == 2
    assert body["counts"]["complete_parent_projected"] == body["counts"]["complete_parent_grammar_quarantined"] == 1
    assert body["rows"][1]["disposition"] == "complete_parent_grammar_quarantine"
    assert body["rows"][1]["quarantine_code"] == "unsupported_complete_submission_grammar"
    assert "projection" not in body["rows"][1] and "transaction_count" not in body["rows"][1]


def test_64_projections_release_each_raw_and_parser_object_before_next(tmp_path, monkeypatch):
    from research.insider_buying import sec_complete_submission as parser
    result, _ = captured(tmp_path, items=[request(i + 1) for i in range(64)])
    original, previous = parser.project_sec_complete_submission, []
    def instrumented(*args):
        gc.collect()
        assert all(ref() is None for ref in previous)
        value = original(*args); previous.append(weakref.ref(value)); return value
    monkeypatch.setattr(parser, "project_sec_complete_submission", instrumented)
    receipt = project(tmp_path, result); gc.collect()
    assert all(ref() is None for ref in previous)
    body = receipt.to_payload()
    assert len(body["rows"]) == body["counts"]["complete_parent_projected"] == 64
    assert [row["global_index"] for row in body["rows"]] == list(range(100, 164))
    assert len(receipt.raw_bytes) < m.MAX_RECEIPT_BYTES


def test_incomplete_capture_refuses_not_empty_projection_ready(tmp_path):
    result, _ = captured(tmp_path, failure=True)
    with pytest.raises(m.FreshV4ProjectionError, match="complete bounded"): project(tmp_path, result)


@pytest.mark.parametrize("leaf", ["complete.json", "reservation.json", "request-000-start.json", "request-000-result.json", "object", "claim"])
def test_custody_substitution_refuses_before_projection(tmp_path, leaf):
    result, _ = captured(tmp_path)
    base = tmp_path.resolve().joinpath(*capture.ARTIFACT_PARTS); run = base / "runs" / result["capture_id"]
    path = (next((run / "objects").iterdir()) if leaf == "object" else
            next((base / "claims").iterdir()) if leaf == "claim" else run / leaf)
    path.write_bytes(b"substituted\n")
    with pytest.raises((m.FreshV4ProjectionError, capture.FreshV4CaptureError, ValueError)):
        project(tmp_path, result)


def test_change_during_projection_refuses_final_independent_replay(tmp_path, monkeypatch):
    from research.insider_buying import sec_complete_submission as parser
    result, _ = captured(tmp_path)
    original = parser.project_sec_complete_submission
    run = tmp_path.resolve().joinpath(*capture.ARTIFACT_PARTS, "runs", result["capture_id"])
    def altered(*args):
        value = original(*args); (run / "complete.json").write_bytes(b"replaced\n"); return value
    monkeypatch.setattr(parser, "project_sec_complete_submission", altered)
    with pytest.raises((m.FreshV4ProjectionError, capture.FreshV4CaptureError, ValueError)):
        project(tmp_path, result)


@pytest.mark.parametrize("changed", ["bytes", "bytearray", "token"])
def test_receipt_mutation_or_detachment_refuses(tmp_path, changed):
    result, _ = captured(tmp_path); receipt = project(tmp_path, result)
    if changed == "token": object.__setattr__(receipt, "_token", object())
    elif changed == "bytearray": object.__setattr__(receipt, "_bytes", bytearray(receipt.raw_bytes))
    else:
        body = receipt.to_payload(); body["counts"]["complete_parent_projected"] = 0
        object.__setattr__(receipt, "_bytes", m._raw(body))
    with pytest.raises(m.FreshV4ProjectionError, match="factory-bound"): receipt.to_payload()


def test_detached_constructor_cannot_make_receipt(tmp_path):
    result, _ = captured(tmp_path); receipt = project(tmp_path, result)
    detached = m.FreshV4ProjectionReceipt(receipt.raw_bytes, receipt._token)
    with pytest.raises(m.FreshV4ProjectionError, match="factory-bound"): detached.to_payload()


def test_registered_receipt_token_cannot_be_rebound_to_equal_impostor(tmp_path):
    result, _ = captured(tmp_path); receipt = project(tmp_path, result)
    class EqualToken:
        def __eq__(self, other): return True
    object.__setattr__(receipt, "_token", EqualToken())
    with pytest.raises(m.FreshV4ProjectionError, match="factory-bound"): receipt.to_payload()


def test_returned_payload_is_detached_from_receipt(tmp_path):
    result, _ = captured(tmp_path); receipt = project(tmp_path, result)
    body = receipt.to_payload(); body["rows"].clear()
    assert len(receipt.to_payload()["rows"]) == 1


def test_regular_import_cannot_claim_source_only_observed_execution():
    with pytest.raises(m.FreshV4ProjectionError, match="source-only"):
        m.replay_observed_first64_v4_projection(expected_report_sha256=m.REPORT_SHA256,
            expected_capture_head=m.CAPTURE_HEAD, projection_repository_head="a" * 40,
            expected_projection_source_sha256="b" * 64)


def test_wrong_observed_capture_cannot_promote_invented_journal(tmp_path):
    result, _ = captured(tmp_path)
    with pytest.raises((m.FreshV4ProjectionError, capture.FreshV4CaptureError, ValueError)):
        m._project_root(result["capture_id"], result["report_sha256"], root=tmp_path.resolve(), observed=True,
            consumer=lambda: pytest.fail("Cannot acquire observed consumer provenance"))


_TOY_BOOTSTRAP = r'''
import hashlib, importlib, os, pathlib, socket, sys, types
path = pathlib.Path(sys.argv[1])
raw = path.read_bytes()
module = types.ModuleType('_projection_bootstrap_toy')
module.__file__ = str(path)
sys.modules[module.__name__] = module
exec(compile(raw, str(path), 'exec', dont_inherit=True), module.__dict__)
if sys.argv[2] == 'preloaded':
    sys.modules['research'] = types.ModuleType('research')
original = importlib.import_module
def controlled(name, *args, **kwargs):
    worker = original(name, *args, **kwargs)
    if name == 'research.insider_buying_sec_recovery_v4_projection':
        def invented_callback(**anchors):
            # Bootstrap/audit proof only. Never call the real root factory and
            # never manufacture a positive observed receipt or source evidence.
            base, sources, finder = worker._SOURCE_CONTEXT
            assert worker.__loader__ is finder and worker.__cached__ is None
            dependency = original('research.insider_buying.sec_complete_submission')
            assert dependency.__loader__ is finder and dependency.__cached__ is None
            assert anchors['expected_projection_source_sha256'] == hashlib.sha256(raw).hexdigest()
            assert len(finder.executed) >= 3
            probes = (lambda: socket.socket(),
                lambda: open('/tmp/INVENTED_FORBIDDEN_PROJECTION_WRITE', 'wb'),
                lambda: os.fork(),
                lambda: original('research.NOT_IN_CAPTURED_SOURCE_INVENTORY'))
            for probe in probes:
                try: probe()
                except base.HistoricalReplayError: pass
                else: raise AssertionError('Audit/source-only refusal was bypassed')
            return types.SimpleNamespace(raw_bytes=b'INVENTED_BOOTSTRAP_ONLY\n')
        worker.replay_observed_first64_v4_projection = invented_callback
    return worker
importlib.import_module = controlled
mode = sys.argv[2]
sys.argv = [str(path), '--expected-report-sha256', module.REPORT_SHA256,
    '--expected-capture-head', module.CAPTURE_HEAD, '--projection-repository-head', 'a'*40,
    '--expected-projection-source-sha256', hashlib.sha256(raw).hexdigest()]
if mode == 'preloaded':
    try: module._main()
    except module.FreshV4ProjectionError as exc:
        assert 'preceded source-only bootstrap' in str(exc)
        print('INVENTED_PRELOAD_REFUSED')
    else: raise AssertionError('Preloaded lane module was accepted')
else: module._main()
'''


@pytest.mark.parametrize("mode", ["clean", "preloaded"])
def test_source_only_cli_bootstrap_and_audit_with_invented_callback_not_actual_root(mode):
    # The child inherits pytest's OS process-tree network denial. The write/
    # fork/socket controls prove the genuine audit hook, not an independent
    # OS all-write/fork proof; main supplies that actual-run sandbox separately.
    result = subprocess.run((sys.executable, "-I", "-S", "-B", "-c", _TOY_BOOTSTRAP,
        str(m.LANE_ROOT / m.SELF_PATH), mode), cwd=m.LANE_ROOT,
        env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"}, capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert result.stdout == (b"INVENTED_BOOTSTRAP_ONLY\n" if mode == "clean" else b"INVENTED_PRELOAD_REFUSED\n")
