"""Invented originals and fresh temporary controls only; never actual artifacts."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

pytest.importorskip("fcntl", reason="IBWIN-CR01: POSIX custody support; Windows custody port deferred")
from research import insider_buying_pilot_sec_parent_structure_runner as m


@pytest.fixture(scope="module")
def supplied():
    spec = importlib.util.spec_from_file_location("invented_structure_runner_originals",
        Path(__file__).with_name("test_insider_buying_sec_complete_submission.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _candidate(supplied, body=None, *, accession=None, root="invented-root", issuer="0000123456"):
    body = supplied._complete() if body is None else body
    target = supplied._target().to_payload()
    raw_target = {key: target[key] for key in ("accession_number", "period", "filing_date", "form_type", "issuer_cik")}
    if accession is not None:
        old = raw_target["accession_number"]
        raw_target["accession_number"] = accession
        target["complete_submission_url"] = target["complete_submission_url"].replace(old.replace("-", ""), accession.replace("-", "")).replace(old, accession)
    raw_target["issuer_cik"] = issuer
    request = {**raw_target, "url": target["complete_submission_url"], "master_source_sha256": "a" * 64,
        "archive_path": target["complete_submission_url"].removeprefix("https://www.sec.gov/Archives/")}
    return {"root_id": root, "control_name": "request-000-result.json", "control_sha256": "b" * 64,
        "request_sha256": m._sha(m._raw(request)), "request": request, "request_url": request["url"],
        "retained_target": raw_target,
        "raw_object": {"relative_path": "objects/" + m._sha(body) + ".bin", "sha256": m._sha(body), "size_bytes": len(body)},
        "body_currently_hash_verified": True, "complete_parent_parsed_here": False}


def _evidence():
    return [{"root_id": "original-root", "journal_sha256": "1" * 64, "state": "ambiguous"},
        {"root_id": "separate-diagnostic", "journal_sha256": "2" * 64, "state": "completed"}]


def _invented(monkeypatch, supplied, *, copies=1, quarantine=False):
    body = supplied._complete()
    if quarantine:
        body = body.replace(b"</SEC-DOCUMENT>\n", b"")
    candidates = [_candidate(supplied, body)]
    for index in range(1, copies):
        item = deepcopy(candidates[0])
        item.update(root_id="invented-copy-" + str(index), control_name="request-copy-result.json", control_sha256="c" * 64)
        # Preserve two producer spellings while normalizing only comparison.
        item["retained_target"]["issuer_cik"] = "123456"
        item["request"]["issuer_cik"] = "123456"
        item["request_sha256"] = m._sha(m._raw(item["request"]))
        candidates.append(item)
    target = candidates[0]["retained_target"]
    registration = deepcopy(m.REGISTRATION)
    registration["expected_distinct_pilot_body_candidates"] = 1
    monkeypatch.setattr(m, "REGISTRATION", registration)
    counts = {period: int(period == target["period"]) for period in m.base.roster.PILOT_PERIODS}
    prior = {"source_roster": {"invented_roster": "metadata-only"}, "parent_audit": {
        "quarters": [{"period": period, "counts": {"hash_verified_matching_body_candidate_targets": count}}
            for period, count in counts.items()],
        "pilot_counts": {"hash_verified_matching_body_candidate_targets": 1}}}
    exposure = {"records": [{"accession_number": target["accession_number"], "evidence": _evidence()}]}
    inventory = {"records": [{"accession_number": target["accession_number"], "candidates": candidates}],
        "masters": [{"period": target["period"], "producer_receipt": {"decoded_sha256": "a" * 64}}]}
    reads = []
    class Tree:
        def read(self, parts, name, *, cap=None, expected=None):
            reads.append((tuple(parts), name, cap, expected))
            assert tuple(parts) == ("objects",)
            assert name == m._sha(body) + ".bin"
            assert cap == m.structure.MAX_BODY_BYTES and expected == m._sha(body)
            return body
    holds = [SimpleNamespace(spec=SimpleNamespace(root_id=item["root_id"]), tree=Tree()) for item in candidates]
    return SimpleNamespace(body=body, candidates=candidates, prior=prior, exposure=exposure, inventory=inventory,
        exposure_raw=m._raw(exposure), retained_raw=m._raw(inventory), holds=holds, reads=reads)


def _derived(fixture):
    return m._derive(fixture.prior, fixture.holds, fixture.exposure_raw, fixture.retained_raw)


def _report(fixture, *, identity=None):
    return {"schema": m.SCHEMA, "audit_id": m.AUDIT_ID, "registration": deepcopy(m.REGISTRATION),
        "registration_sha256": m._sha(m._raw(m.REGISTRATION)),
        "execution_identity": {"invented": True} if identity is None else identity,
        "prior_audit_complete_sha256": m.PINS["complete.json"][0],
        "exposure_inventory_sha256": m._sha(fixture.exposure_raw),
        "retained_inventory_sha256": m._sha(fixture.retained_raw), "result": _derived(fixture),
        "authority": dict(m.base.compiler._AUTHORITY), "native_network_fork_allwrite_securityexec_denial": True,
        "new_provider_requests": 0, "credential_reads": 0, "qc_accesses": 0,
        "financial_numeric_fields_converted": False, "canonical_admitted": False, "backtesting_ready": False}


def _rehash(report):
    raw = b"".join(m._raw(row) + b"\n" for row in report["result"]["structural_records"])
    report["result"]["ordered_structural_jsonl_sha256"] = m._sha(raw)
    report["result"]["ordered_structural_jsonl_bytes"] = len(raw)


def test_fresh_scope_and_registration_are_stable_without_new_acquisition_or_authority():
    assert m.AUDIT_ID != m.base.AUDIT_ID and m.OUTPUT_PARTS != m.base.OUTPUT_PARTS
    assert m.REGISTRATION == json.loads(m._raw(m.REGISTRATION))
    assert m.REGISTRATION["expected_distinct_pilot_body_candidates"] == 19852
    assert m.REGISTRATION["prior_existing_execution_head"] == "b33cf144153fd118add3acdc6a9caad22b8b4077"
    assert m.REGISTRATION["worker_invocations"] == 1
    for key in ("new_provider_requests", "credential_reads", "outcome_looks", "backtests"):
        assert type(m.REGISTRATION[key]) is int and m.REGISTRATION[key] == 0
    for key in ("qc_access", "backtesting_ready", "original_financial_numeric_fields_converted",
            "ambiguous_prior_requests_resolved_or_retried"):
        assert m.REGISTRATION[key] is False
    assert m.REGISTRATION["prior_audit_pins"] == {name: {"sha256": digest, "bytes": size} for name, (digest, size) in m.PINS.items()}


def test_derive_real_factory_result_once_for_identical_physical_copies(monkeypatch, supplied):
    fixture = _invented(monkeypatch, supplied, copies=2)
    parsed = []
    def process(body, candidate, **kwargs):
        parsed.append((body, deepcopy(candidate), deepcopy(kwargs)))
        return m.structure.process_candidate(body, candidate, **kwargs)
    result = m._derive(fixture.prior, fixture.holds, fixture.exposure_raw, fixture.retained_raw, process=process)
    assert len(parsed) == len(fixture.reads) == 1
    assert parsed[0][2] == {"expected_candidate_sha256": m._sha(m._raw(fixture.candidates[0])),
        "expected_body_sha256": m._sha(fixture.body), "expected_master_decoded_sha256": "a" * 64,
        "prior_exposure_evidence": _evidence()}
    assert result["counts"] == {"candidates": 1, "structurally_bound": 1, "structure_quarantined": 0,
        "historical_ambiguous_start_preserved": 1}
    wrapped = result["structural_records"][0]
    assert len(wrapped["all_matching_evidence"]) == 2
    assert [row["retained_target"]["issuer_cik"] for row in wrapped["all_matching_evidence"]] == ["0000123456", "123456"]
    assert wrapped["structure"]["original_unmatched_start_resolved"] is False
    assert wrapped["structure"]["canonical_or_ib1c_identity_admitted"] is False
    assert b"<ownershipDocument>" not in m._raw(result)
    assert b"<SEC-HEADER>" not in m._raw(result)
    raw = m._raw(wrapped) + b"\n"
    assert result["ordered_structural_jsonl_sha256"] == m._sha(raw)
    assert result["ordered_structural_jsonl_bytes"] == len(raw)
    assert set(result["quarter_counts"]) == set(m.base.roster.PILOT_PERIODS)


def test_genuine_parser_refusal_remains_quarantined_and_consumed(monkeypatch, supplied):
    fixture = _invented(monkeypatch, supplied, quarantine=True)
    result = _derived(fixture)
    assert result["counts"] == {"candidates": 1, "structurally_bound": 0, "structure_quarantined": 1,
        "historical_ambiguous_start_preserved": 1}
    row = result["structural_records"][0]["structure"]
    assert row["quarantine_code"] == m.structure.QUARANTINE_CODE
    assert row["frozen_projection_sha256"] is row["children"] is row["source_declared_fields"] is None
    assert row["consumed_accession_released_for_redispatch"] is False
    assert row["historical_ambiguous_start_preserved"] is True


@pytest.mark.parametrize("change", [
    lambda item: item.update(body_currently_hash_verified=False),
    lambda item: item.update(body_currently_hash_verified=1),
    lambda item: item.update(request_url="https://www.sec.gov/Archives/another.txt"),
    lambda item: item["raw_object"].update(sha256="0" * 64),
    lambda item: item["raw_object"].update(size_bytes=999),
    lambda item: item["retained_target"].update(form_type="4/A"),
    lambda item: item["retained_target"].update(issuer_cik="999999"),
])
def test_competing_nonidentical_or_unverified_copies_are_not_selected(monkeypatch, supplied, change):
    fixture = _invented(monkeypatch, supplied, copies=2)
    change(fixture.inventory["records"][0]["candidates"][1])
    with pytest.raises(m.StructureRunnerError, match="unanimity"):
        m._pilot_records(fixture.inventory)


def test_nonpilot_copy_is_not_silently_promoted_or_counted(monkeypatch, supplied):
    fixture = _invented(monkeypatch, supplied)
    other = deepcopy(fixture.inventory["records"][0])
    other["accession_number"] = "0000999999-20-000001"
    other["candidates"][0]["retained_target"]["period"] = "2020Q4"
    fixture.inventory["records"].append(other)
    assert len(m._pilot_records(fixture.inventory)) == 1
    m.REGISTRATION["expected_distinct_pilot_body_candidates"] = 2
    with pytest.raises(m.StructureRunnerError, match="exact_audited"):
        m._pilot_records(fixture.inventory)


@pytest.mark.parametrize("fault", ["no_evidence", "no_master", "quarter_count", "pilot_count", "body_size"])
def test_derive_refuses_missing_evidence_or_incomplete_conservation(monkeypatch, supplied, fault):
    fixture = _invented(monkeypatch, supplied)
    exposure, inventory = deepcopy(fixture.exposure), deepcopy(fixture.inventory)
    if fault == "no_evidence": exposure["records"] = []
    if fault == "no_master": inventory["masters"] = []
    if fault == "quarter_count":
        for row in fixture.prior["parent_audit"]["quarters"]:
            if row["period"] == "2022Q4": row["counts"]["hash_verified_matching_body_candidate_targets"] = 2
    if fault == "pilot_count": fixture.prior["parent_audit"]["pilot_counts"]["hash_verified_matching_body_candidate_targets"] = 2
    if fault == "body_size": inventory["records"][0]["candidates"][0]["raw_object"]["size_bytes"] += 1
    with pytest.raises(m.StructureRunnerError):
        m._derive(fixture.prior, fixture.holds, m._raw(exposure), m._raw(inventory))


def test_factory_cannot_be_replaced_with_a_metadata_shaped_object(monkeypatch, supplied):
    fixture = _invented(monkeypatch, supplied)
    with pytest.raises(m.structure.PilotSecParentStructureError):
        m._derive(fixture.prior, fixture.holds, fixture.exposure_raw, fixture.retained_raw,
            process=lambda *_a, **_k: SimpleNamespace(to_payload=lambda: {"full_original_structurally_bound": True}))


@pytest.mark.parametrize("quarantine", [False, True])
def test_parent_accepts_exact_serialized_factory_result(monkeypatch, supplied, quarantine):
    fixture = _invented(monkeypatch, supplied, quarantine=quarantine)
    report = m.base._decode(m._raw(_report(fixture)))
    assert m._validate(report, {"invented": True}) is report


@pytest.mark.parametrize("change", [
    lambda report: report.update(unexpected="PRIVATE"),
    lambda report: report.update(execution_identity={"other": True}),
    lambda report: report.update(prior_audit_complete_sha256="0" * 64),
    lambda report: report.update(registration_sha256="0" * 64),
    lambda report: report.update(native_network_fork_allwrite_securityexec_denial=False),
    lambda report: report.update(credential_reads=False),
    lambda report: report.update(new_provider_requests=1),
    lambda report: report.update(qc_accesses=1),
    lambda report: report.update(backtesting_ready=True),
    lambda report: report.update(canonical_admitted=0),
    lambda report: report.update(financial_numeric_fields_converted=True),
    lambda report: report["authority"].update(dispatch_enabled=True),
    lambda report: report["authority"].update(dispatch_enabled=0.0),
    lambda report: report["result"].update(source_filings_not_redecoded_here=False),
    lambda report: report["result"].update(extra=True),
    lambda report: report["result"]["counts"].update(candidates=True),
    lambda report: report["result"]["counts"].update(structurally_bound=0),
    lambda report: report["result"].update(ordered_structural_jsonl_sha256="0" * 64),
    lambda report: report["result"].update(ordered_structural_jsonl_bytes=1),
    lambda report: report["result"]["quarter_counts"].pop("2021Q1"),
    lambda report: report["result"]["quarter_counts"]["2022Q4"].update(candidates=True),
    lambda report: report["result"]["quarter_counts"]["2022Q4"].update(structurally_bound=1.0),
])
def test_parent_refuses_root_authority_identity_and_complete_count_laundering(monkeypatch, supplied, change):
    report = _report(_invented(monkeypatch, supplied))
    change(report)
    with pytest.raises((m.StructureRunnerError, ValueError)):
        m._validate(report, {"invented": True})


@pytest.mark.parametrize("change", [
    lambda item: item.update(unexpected="PRIVATE"),
    lambda item: item.update(scope="canonical_acceptance"),
    lambda item: item.update(frozen_parser_version="unbound-parser"),
    lambda item: item.update(original_unmatched_start_resolved=True),
    lambda item: item.update(consumed_accession_released_for_redispatch=True),
    lambda item: item.update(raw_request_target_rewritten=True),
    lambda item: item.update(named_file_custody_verified_here=True),
    lambda item: item.update(source_declared_acceptance_is_not_official_or_pit=False),
    lambda item: item.update(xml_financial_text_may_be_structurally_decoded=False),
    lambda item: item.update(canonical_or_ib1c_identity_admitted=True),
    lambda item: item.update(financial_values_projected=True),
    lambda item: item.update(historical_ambiguous_start_preserved=False),
    lambda item: item.update(historical_ambiguous_start_preserved=1),
    lambda item: item.update(ownership_xml_identity_structurally_checked=False),
    lambda item: item.update(disposition="canonical_admitted"),
    lambda item: item.update(quarantine_code=m.structure.QUARANTINE_CODE),
    lambda item: item["request"].update(issuer_cik="999"),
    lambda item: item["authority"].update(dispatch_enabled=True),
])
def test_parent_deep_scope_and_ambiguity_checks_are_not_just_stream_hashes(monkeypatch, supplied, change):
    report = _report(_invented(monkeypatch, supplied))
    change(report["result"]["structural_records"][0]["structure"])
    _rehash(report)
    with pytest.raises((m.StructureRunnerError, ValueError)):
        m._validate(report, {"invented": True})


def test_parent_refuses_duplicate_accession_even_with_recomputed_framing(monkeypatch, supplied):
    report = _report(_invented(monkeypatch, supplied))
    report["result"]["structural_records"].append(deepcopy(report["result"]["structural_records"][0]))
    _rehash(report)
    with pytest.raises(m.StructureRunnerError, match="accession_order_or_repeat"):
        m._validate(report, {"invented": True})


@pytest.mark.parametrize("fault", ["no_evidence", "body_sha", "body_size", "extra"])
def test_parent_rejects_matching_evidence_body_detachment(monkeypatch, supplied, fault):
    report = _report(_invented(monkeypatch, supplied))
    row = report["result"]["structural_records"][0]
    if fault == "no_evidence": row["all_matching_evidence"] = []
    elif fault == "body_sha": row["all_matching_evidence"][0]["raw_object"]["sha256"] = "0" * 64
    elif fault == "body_size": row["all_matching_evidence"][0]["raw_object"]["size_bytes"] += 1
    else: row["all_matching_evidence"][0]["extra"] = "PRIVATE"
    _rehash(report)
    with pytest.raises(m.StructureRunnerError): m._validate(report, {"invented": True})


@pytest.mark.parametrize("change", [
    lambda row: row["all_matching_evidence"][0]["retained_target"].update(period="2021Q1"),
    lambda row: row["all_matching_evidence"][0]["retained_target"].update(issuer_cik="999999"),
    lambda row: row["all_matching_evidence"][0].update(request_url="https://www.sec.gov/Archives/another.txt"),
    lambda row: row["all_matching_evidence"][0].update(control_sha256="f" * 64),
    lambda row: row["all_matching_evidence"][0].update(request_sha256="f" * 64),
    lambda row: row["all_matching_evidence"][0].update(control_name="another-result.json"),
    lambda row: row["structure"]["retained_control"].update(root_id="detached-root"),
    lambda row: row["structure"]["frozen_parser_comparison_target"].update(issuer_cik="0000999999"),
    lambda row: row["structure"].update(expected_master_decoded_sha256="f" * 64),
    lambda row: row["structure"].update(issuer_comparison_padding_applied=True),
    lambda row: row["structure"]["children"]["header"].update(parent_sha256="f" * 64),
    lambda row: row["structure"].update(frozen_projection_sha256="not-a-digest"),
])
def test_parent_checks_source_lineage_even_after_full_stream_rehash(monkeypatch, supplied, change):
    report = _report(_invented(monkeypatch, supplied))
    change(report["result"]["structural_records"][0])
    _rehash(report)
    with pytest.raises((m.StructureRunnerError, ValueError)):
        m._validate(report, {"invented": True})


def _two_records(monkeypatch, supplied):
    fixture = _invented(monkeypatch, supplied)
    other = _candidate(supplied, fixture.body, accession="0000999999-22-000002")
    fixture.inventory["records"].append({"accession_number": other["retained_target"]["accession_number"], "candidates": [other]})
    fixture.exposure["records"].append({"accession_number": other["retained_target"]["accession_number"], "evidence": _evidence()})
    fixture.exposure_raw, fixture.retained_raw = m._raw(fixture.exposure), m._raw(fixture.inventory)
    m.REGISTRATION["expected_distinct_pilot_body_candidates"] = 2
    fixture.prior["parent_audit"]["pilot_counts"]["hash_verified_matching_body_candidate_targets"] = 2
    for row in fixture.prior["parent_audit"]["quarters"]:
        if row["period"] == other["retained_target"]["period"]:
            row["counts"]["hash_verified_matching_body_candidate_targets"] = 2
    return fixture


def test_full_two_record_accounting_includes_real_structure_quarantine(monkeypatch, supplied):
    fixture = _two_records(monkeypatch, supplied)
    report = _report(fixture)
    assert report["result"]["counts"] == {"candidates": 2, "structurally_bound": 1, "structure_quarantined": 1,
        "historical_ambiguous_start_preserved": 2}
    assert m._validate(report, {"invented": True}) == report
    assert report["result"]["quarter_counts"]["2022Q4"] == {
        "candidates": 2, "structurally_bound": 1, "structure_quarantined": 1}


def test_claimed_accession_order_cannot_be_changed_by_rehashing(monkeypatch, supplied):
    report = _report(_two_records(monkeypatch, supplied))
    report["result"]["structural_records"].reverse()
    _rehash(report)
    with pytest.raises(m.StructureRunnerError): m._validate(report, {"invented": True})


def _guard():
    command = ("/usr/bin/env", "-i", "PATH=/usr/bin:/bin", sys.executable, "-I", "-S", "-B", "-c", "pass")
    return m._Guard("a" * 40, command), command


def test_new_parent_guard_keeps_old_scope_readonly_and_exact_one_worker():
    guard, command = _guard()
    assert guard.output == m.LANE_ROOT.joinpath(*m.OUTPUT_PARTS, m.AUDIT_ID)
    old = m.LANE_ROOT.joinpath(*m.base.OUTPUT_PARTS, m.base.AUDIT_ID)
    with pytest.raises(m.base.PilotParentRunnerError): guard._write(old / "complete.json")
    for name in ("reservation.json", "terminal.json", "complete.json"):
        guard._write(guard.output / name)
    with pytest.raises(m.base.PilotParentRunnerError): guard._write(guard.output / "raw-original.bin")
    guard("subprocess.Popen", (command[0], command, m.LANE_ROOT, None))
    with pytest.raises(m.base.PilotParentRunnerError):
        guard("subprocess.Popen", (command[0], command, m.LANE_ROOT, None))


@pytest.mark.parametrize("fault", ["command", "cwd", "environment", "executable"])
def test_parent_guard_refuses_alternate_or_ambient_worker_dispatch(fault):
    guard, command = _guard()
    executable, cwd, env = command[0], m.LANE_ROOT, None
    if fault == "command": command = (*command, "changed")
    if fault == "cwd": cwd = m.LANE_ROOT.parent
    if fault == "environment": env = {"TOKEN": "PRIVATE"}
    if fault == "executable": executable = "/usr/bin/security"
    with pytest.raises(m.base.PilotParentRunnerError): guard("subprocess.Popen", (executable, command, cwd, env))


@pytest.mark.parametrize("event", ["socket.connect", "urllib.Request", "os.exec", "os.posix_spawn", "os.system", "os.fork"])
def test_parent_guard_network_and_unapproved_exec_are_denied(event):
    guard, _ = _guard()
    with pytest.raises(PermissionError): guard(event, ())


def test_worker_native_flags_are_checked_before_inputs(monkeypatch):
    monkeypatch.setattr(m, "_PriorHold", lambda: pytest.fail("old controls must not be opened"))
    # Ordinary pytest intentionally does not use -S; no actual input is touched.
    with pytest.raises(m.StructureRunnerError, match="isolated_structure_worker"):
        m._worker({"invented": True})


def _prior_controls(monkeypatch):
    report = {"execution_identity": {"head": m.REGISTRATION["prior_existing_execution_head"]}, "invented": True}
    leaves = {"reservation.json": b'{"invented":"reservation"}', "terminal.json": b'{"invented":"terminal"}',
        "complete.json": m._raw(report)}
    pins = {name: (m._sha(raw), len(raw)) for name, raw in leaves.items()}
    monkeypatch.setattr(m, "PINS", pins)
    captured = []
    class Tree:
        def __init__(self, path, *, private, settle_ctime):
            assert path == m.LANE_ROOT.joinpath(*m.base.OUTPUT_PARTS, m.base.AUDIT_ID)
            assert private is settle_ctime is True
            self.names, self.handles = set(leaves), []
            self.checks = 0
            captured.append(self)
        def open(self, name, cap):
            assert cap == len(leaves[name])
            self.handles.append((name, io.BytesIO(leaves[name]), None, cap))
        def check(self): self.checks += 1
    def close(tree, *, phase):
        assert phase == "structure_prior_cleanup"
        if tree is not None:
            for _name, stream, _version, _cap in tree.handles: stream.close()
    monkeypatch.setattr(m.base.selector.held_io, "_HeldCapture", Tree)
    monkeypatch.setattr(m.base.selector, "_close_tree", close)
    validations = []
    def validate(value, identity):
        assert value == report and identity == report["execution_identity"]
        validations.append(True)
    monkeypatch.setattr(m.base, "_validate_result", validate)
    return report, leaves, captured, validations


def test_old_audit_controls_are_pinned_rechecked_and_deeply_validated(monkeypatch):
    report, _leaves, captured, validations = _prior_controls(monkeypatch)
    hold = m._PriorHold()
    try:
        assert hold.report() == report and validations == [True]
        assert set(name for name, *_ in captured[0].handles) == set(m.PINS)
        before = captured[0].checks
        hold.recheck()
        assert captured[0].checks == before + 2
    finally: hold.close()
    assert all(stream.closed for _name, stream, _version, _cap in captured[0].handles)


@pytest.mark.parametrize("fault", ["inventory", "content", "head", "deep_validation"])
def test_prior_failed_or_changed_audit_cannot_be_substituted(monkeypatch, fault):
    report, leaves, captured, _ = _prior_controls(monkeypatch)
    if fault == "inventory":
        leaves["extra.json"] = b"{}"
        with pytest.raises(m.StructureRunnerError, match="prior_control_inventory"): m._PriorHold()
        return
    hold = m._PriorHold()
    try:
        if fault == "content":
            for name, stream, _version, _cap in captured[0].handles:
                if name == "terminal.json": stream.seek(0); stream.write(b"x")
            with pytest.raises(m.StructureRunnerError, match="hash_changed"): hold.recheck()
        elif fault == "head":
            registration = deepcopy(m.REGISTRATION)
            registration["prior_existing_execution_head"] = "f" * 40
            monkeypatch.setattr(m, "REGISTRATION", registration)
            with pytest.raises(m.StructureRunnerError, match="prior_execution_head"): hold.report()
        else:
            def refusal(*_): raise m.base.PilotParentRunnerError("invented_old_result_refusal")
            monkeypatch.setattr(m.base, "_validate_result", refusal)
            with pytest.raises(m.base.PilotParentRunnerError): hold.report()
    finally: hold.close()


def _worker_fixture(monkeypatch, supplied):
    fixture = _invented(monkeypatch, supplied)
    source = {m.SELF_PATH: "d" * 64}
    identity = {"root": str(m.LANE_ROOT), "branch": m.base.LANE_BRANCH, "clean": True,
        "source_sha256": source, "source_inventory_sha256": m._sha(m._raw(source))}
    fixture.prior.update(exposure_inventory_sha256=m._sha(fixture.exposure_raw),
        exposure_snapshot_sha256=m._sha(b'{"invented":"snapshot"}'), retained_body_inventory_sha256=m._sha(fixture.retained_raw))
    calls = []
    monkeypatch.setattr(m, "sys", SimpleNamespace(flags=SimpleNamespace(isolated=1, no_site=1, dont_write_bytecode=1),
        pycache_prefix=m.base.EMPTY_CACHE_PREFIX))
    monkeypatch.setattr(m.base, "_prove_isolation", lambda: calls.append("native_proof"))
    def sources(_root, paths):
        calls.append("frozen_sources" if tuple(paths) == tuple(m.base.FROZEN) else "current_sources")
        return dict(m.base.FROZEN) if tuple(paths) == tuple(m.base.FROZEN) else dict(source)
    monkeypatch.setattr(m.base.custody, "_source_bytes", sources)
    class Prior:
        def report(self): calls.append("prior_report"); return fixture.prior
        def recheck(self): calls.append("prior_recheck")
        def close(self): calls.append("prior_close")
    monkeypatch.setattr(m, "_PriorHold", Prior)
    for hold in fixture.holds:
        hold.recheck = lambda: calls.append("body_recheck")
        hold.close = lambda: calls.append("body_close")
    monkeypatch.setattr(m.base.exposure, "actual_roots", lambda: ("invented-root",))
    def observe(roots, *, fixture_only):
        assert roots == ("invented-root",) and fixture_only is False
        calls.append("observe")
        return fixture.holds, fixture.exposure_raw, b'{"invented":"snapshot"}', fixture.retained_raw
    monkeypatch.setattr(m.base.exposure, "observe_exposures", observe)
    def hash_bodies(holds, raw):
        assert holds == fixture.holds and raw == fixture.retained_raw
        calls.append("hash_bodies")
        return raw
    monkeypatch.setattr(m.base.exposure, "hash_candidate_bodies", hash_bodies)
    return fixture, identity, calls


def test_worker_proves_native_denial_before_sources_and_rechecks_after_structure(monkeypatch, supplied):
    _fixture, identity, calls = _worker_fixture(monkeypatch, supplied)
    report = m._worker(identity)
    assert calls[0] == "native_proof"
    assert calls.count("current_sources") == 2 and calls.count("frozen_sources") == 1
    assert calls.index("hash_bodies") < calls.index("body_recheck") < calls.index("prior_recheck")
    assert calls[-2:] == ["prior_close", "body_close"]
    assert m._validate(report, identity) == report


@pytest.mark.parametrize("fault", ["root", "branch", "dirty", "source_digest", "native_proof", "exposure_snapshot", "body_inventory"])
def test_worker_fail_closed_before_derived_results_and_closes_owned_inputs(monkeypatch, supplied, fault):
    fixture, identity, calls = _worker_fixture(monkeypatch, supplied)
    if fault == "root": identity["root"] = str(m.LANE_ROOT.parent)
    if fault == "branch": identity["branch"] = "codex/not-this-lane"
    if fault == "dirty": identity["clean"] = False
    if fault == "source_digest": identity["source_inventory_sha256"] = "f" * 64
    if fault == "native_proof":
        def refuse(): raise m.base.PilotParentRunnerError("native_denial_not_effective")
        monkeypatch.setattr(m.base, "_prove_isolation", refuse)
    if fault == "exposure_snapshot": fixture.prior["exposure_snapshot_sha256"] = "f" * 64
    if fault == "body_inventory": fixture.prior["retained_body_inventory_sha256"] = "f" * 64
    with pytest.raises((m.StructureRunnerError, m.base.PilotParentRunnerError)): m._worker(identity)
    if fault in {"root", "branch", "dirty", "source_digest", "native_proof"}:
        assert "observe" not in calls
    else:
        assert "prior_close" in calls and "body_close" in calls


def _orchestration(monkeypatch, supplied):
    fixture = _invented(monkeypatch, supplied)
    identity = {"invented": True, "source_sha256": {m.SELF_PATH: "a" * 64}}
    report = _report(fixture, identity=identity)
    calls = {"identity": [], "child": [], "published": {}, "final": [], "closed": []}
    def identify(head): calls["identity"].append(head); return deepcopy(identity)
    monkeypatch.setattr(m.base.custody, "_identity", identify)
    monkeypatch.setattr(m.sys, "addaudithook", lambda _: None)
    class Chain:
        def __init__(self, root, parts):
            assert root == m.LANE_ROOT
            self.fd = 123
            self.parts = parts
        def recheck(self): pass
        def close(self): calls["closed"].append(self.parts)
    monkeypatch.setattr(m.base.custody, "_Chain", Chain)
    monkeypatch.setattr(m.os, "mkdir", lambda *_a, **_k: None)
    monkeypatch.setattr(m.os, "fstatvfs", lambda _: SimpleNamespace(f_bavail=1 << 32, f_frsize=4096))
    class Output:
        def __init__(self, chain):
            assert chain.parts == (*m.OUTPUT_PARTS, m.AUDIT_ID)
        def publish(self, name, raw):
            assert name not in calls["published"]
            calls["published"][name] = m.base._decode(raw)
            return m._sha(raw)
        def recheck(self, *, final=False): calls["final"].append(final)
        def close(self): calls["closed"].append("output")
    monkeypatch.setattr(m, "_Output", Output)
    def child(command, **kwargs):
        calls["child"].append((command, kwargs))
        assert command[:2] == ("/usr/bin/env", "-i")
        assert command[2] == "PATH=/usr/bin:/bin:/usr/sbin:/sbin"
        assert command[3:5] == ("/usr/bin/sandbox-exec", "-p")
        assert all(deny in command[5] for deny in ("(deny network*)", "(deny process-fork)", "(deny file-write*)",
            '(deny process-exec (literal "/usr/bin/security"))'))
        assert command[6] == sys.executable and command[7:10] == ("-I", "-S", "-B")
        assert "pycache_prefix=" + m.base.EMPTY_CACHE_PREFIX in command
        assert kwargs == {"cwd": m.LANE_ROOT, "env": None, "timeout": 1800, "cap": m.base.MAX_REPORT}
        assert "reservation.json" in calls["published"] and "terminal.json" not in calls["published"]
        return subprocess.CompletedProcess(command, 0, m._raw(report) + b"\n", b"")
    monkeypatch.setattr(m.base.launcher, "run_child", child)
    return fixture, identity, report, calls


def test_parent_claims_new_scope_once_and_publishes_verified_full_report(monkeypatch, supplied):
    _, _, report, calls = _orchestration(monkeypatch, supplied)
    old_registration = deepcopy(m.base.REGISTRATION)
    receipt = m.run_actual("a" * 40)
    assert len(calls["child"]) == 1 and calls["identity"] == ["a" * 40, "a" * 40]
    assert list(calls["published"]) == ["reservation.json", "terminal.json", "complete.json"]
    assert calls["published"]["complete.json"] == report
    assert calls["final"] == [True] and "output" in calls["closed"]
    assert receipt["complete_sha256"] == m._sha(m._raw(report))
    assert receipt["complete_bytes"] == len(m._raw(report))
    terminal = calls["published"]["terminal.json"]
    assert terminal["exit_code"] == 0 and terminal["stderr_bytes"] == 0
    assert terminal["stdout_sha256"] == m._sha(m._raw(report) + b"\n")
    assert "args" not in terminal and "stderr" not in terminal and "stdout" not in terminal
    assert receipt["backtesting_ready"] is False and m.base.REGISTRATION == old_registration


@pytest.mark.parametrize("fault", ["exit", "stderr", "empty", "malformed", "changed_identity", "result_authority", "final_readback"])
def test_parent_refusal_never_returns_success_or_publishes_private_child_text(monkeypatch, supplied, fault):
    _, identity, report, calls = _orchestration(monkeypatch, supplied)
    original = m.base.launcher.run_child
    if fault in {"exit", "stderr", "empty", "malformed"}:
        def child(command, **kwargs):
            original(command, **kwargs)
            return subprocess.CompletedProcess(command, 2 if fault == "exit" else 0,
                b"" if fault == "empty" else b"PRIVATE MALFORMED" if fault == "malformed" else m._raw(report) + b"\n",
                b"PRIVATE STDERR" if fault == "stderr" else b"")
        monkeypatch.setattr(m.base.launcher, "run_child", child)
    if fault == "changed_identity":
        values = iter([identity, {**identity, "invented": "changed"}])
        monkeypatch.setattr(m.base.custody, "_identity", lambda _: next(values))
    if fault == "result_authority": report["backtesting_ready"] = True
    if fault == "final_readback":
        class BrokenOutput(m._Output):
            def recheck(self, *, final=False):
                assert final
                raise ValueError("PRIVATE readback refusal")
        monkeypatch.setattr(m, "_Output", BrokenOutput)
    with pytest.raises((m.StructureRunnerError, ValueError)):
        m.run_actual("a" * 40)
    if fault not in {"final_readback"}:
        assert "complete.json" not in calls["published"]
    assert "output" in calls["closed"]
    terminal_raw = m._raw(calls["published"]["terminal.json"])
    assert b"PRIVATE" not in terminal_raw


def test_actual_cli_refusal_is_sanitized_and_nonzero(monkeypatch, capsys):
    def refuse(_): raise ValueError("PRIVATE credential source path and body")
    monkeypatch.setattr(m, "run_actual", refuse)
    assert m.main(["--expected-head", "a" * 40]) == 2
    assert capsys.readouterr().out == '{"disposition":"pilot_parent_structure_refused"}\n'


def _publication(monkeypatch, tmp_path):
    os.chmod(tmp_path, 0o700)
    path = tmp_path.joinpath(*m.OUTPUT_PARTS, m.AUDIT_ID)
    path.mkdir(parents=True, mode=0o700)
    monkeypatch.setattr(m, "LANE_ROOT", tmp_path)
    chain = m.base.custody._Chain(path, ())
    return path, chain, m._Output(chain)


def test_new_output_is_private_exclusive_fullhash_and_three_leaves(monkeypatch, tmp_path):
    path, chain, output = _publication(monkeypatch, tmp_path)
    try:
        output.publish("reservation.json", b'{"invented":"reservation"}')
        with pytest.raises(m.base.PilotParentRunnerError, match="incomplete"): output.recheck(final=True)
        output.publish("terminal.json", b'{"invented":"terminal"}')
        output.publish("complete.json", b'{"invented":"complete"}')
        output.recheck(final=True)
        assert set(os.listdir(path)) == {"reservation.json", "terminal.json", "complete.json"}
        assert all((path / name).stat().st_mode & 0o777 == 0o600 for name in os.listdir(path))
        with pytest.raises(m.StructureRunnerError, match="cannot_resume"): m._Output(chain)
        with pytest.raises(m.base.PilotParentRunnerError): output.publish("complete.json", b"{}")
    finally:
        output.close(); chain.close()


@pytest.mark.parametrize("fault", ["content", "replacement", "mode", "extra"])
def test_published_control_mutation_cannot_hide_behind_prior_hash(monkeypatch, tmp_path, fault):
    path, chain, output = _publication(monkeypatch, tmp_path)
    try:
        output.publish("reservation.json", b'{"invented":"a"}')
        leaf = path / "reservation.json"
        version = leaf.stat()
        if fault == "content":
            leaf.write_bytes(b'{"invented":"b"}')
            os.utime(leaf, ns=(version.st_atime_ns, version.st_mtime_ns))
        elif fault == "replacement":
            new = path / "replacement"
            new.write_bytes(leaf.read_bytes()); os.chmod(new, 0o600); os.replace(new, leaf)
        elif fault == "mode": os.chmod(leaf, 0o644)
        else: (path / "extra").write_bytes(b"PRIVATE")
        with pytest.raises((m.base.PilotParentRunnerError, ValueError)): output.recheck()
    finally:
        output.close(); chain.close()


def test_real_new_guard_call_stack_permits_only_known_child_devnull_sink():
    script = ("import sys;sys.path.insert(0," + repr(str(m.LANE_ROOT)) + ");"
        "from research import insider_buying_pilot_sec_parent_structure_runner as m;"
        "cmd=('/usr/bin/env','-i','PATH=/usr/bin:/bin',sys.executable,'-I','-S','-B','-c','print(123)');"
        "sys.addaudithook(m._Guard('a'*40,cmd));"
        "r=m.base.launcher.run_child(cmd,cwd=m.LANE_ROOT,env=None,timeout=10,cap=1024);"
        "assert r.returncode==0 and r.stdout==b'123\\n' and r.stderr==b'';print('new_scope_guard_passed')")
    child = subprocess.run((sys.executable, "-I", "-S", "-B", "-c", script),
        capture_output=True, cwd=m.LANE_ROOT, env={"PATH": "/usr/bin:/bin"}, timeout=20)
    assert child.returncode == 0, child.stderr.decode()
    assert child.stdout == b"new_scope_guard_passed\n"
