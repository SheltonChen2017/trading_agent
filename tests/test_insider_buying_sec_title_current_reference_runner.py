"""Invented temporary source-only runner checks; no account or actual inputs."""
from __future__ import annotations

import copy
import base64
import importlib.util
import json
import os
from pathlib import Path
import sys
import subprocess
from types import SimpleNamespace

import pytest

pytest.importorskip("fcntl", reason="validated macOS/POSIX custody stack")
DIR = Path(__file__).parent
LANE = Path("/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__insider_buying")
sys.path.insert(0, str(LANE / "tests"))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


from research import insider_buying_sec_title_current_reference_v1 as pure
from research import insider_buying_sec_title_current_reference_runner as module
import test_insider_buying_sec_title_current_reference_v1 as fixtures
supplied = fixtures.supplied
import test_insider_buying_sec_2006q1_pem_reassessment_runner as preceding_fixtures


def _context():
    return {"identity": {"head": "a" * 40, "source_sha256": {}}, "frozen_sources": {},
        "source_view_context": {"full_ordered_source_identity": {"source_filings": 6, "target_filings": 2,
            "context_filings": 4}, "counts": {"source_filings": 6, "target_filings": 2, "context_filings": 4,
            "selected_parents": 1, "frozen_source_view_projections": 1, "source_view_parser_quarantined": 0},
            "capture_context": {}},
        "sharadar_context": {"counts": {"source_ticker_rows": 3}}}


def _counts():
    counts = {key: 0 for key in pure.COUNT_KEYS}
    counts.update(source_filings=6, target_filings=2, context_filings=4, selected_parents=1,
        genuine_view_parents=1, unselected_filings=5, genuine_parents_without_nonderivative_rows=1,
        ticker_rows=3, ticker_rows_without_cik_candidates=3)
    return counts


def _summary():
    return {"audit_id": "ib-sec-title-current-reference-invented", "fixture_only": True,
        "complete_sha256": "a" * 64, "assessment_sha256": "b" * 64, "counts": _counts(),
        "title_refusal_counts": dict.fromkeys(pure.TITLE_REFUSAL_CODES, 0),
        "ticker_refusal_counts": dict.fromkeys(pure.TICKER_REFUSAL_CODES, 0), "authority": pure._authority()}


@pytest.mark.parametrize("kind", ["population", "target_partition", "selection", "genuine", "parser_refusal", "ticker_population",
    "title_partition", "ticker_partition", "title_index_partition", "group_bound", "bool_zero"])
def test_summary_cannot_choose_its_own_population_or_partition(kind):
    body = _summary()
    key, value = {"population": ("source_filings", 7), "target_partition": ("target_filings", 3),
        "selection": ("selected_parents", 2), "genuine": ("genuine_view_parents", 0),
        "parser_refusal": ("parser_refused_selected_parents", 1), "ticker_population": ("ticker_rows", 4),
        "title_partition": ("plain_title_occurrences", 1), "ticker_partition": ("ticker_rows_with_cik_candidates", 1),
        "title_index_partition": ("titles_without_current_cik_groups", 1), "group_bound": ("current_permaticker_groups", 4),
        "bool_zero": ("title_occurrences", False)}[kind]
    body["counts"][key] = value
    with pytest.raises(ValueError):
        module._validate_summary(body, audit_id=body["audit_id"], context=_context(), fixture_only=True)


def _write_publication(tmp_path, monkeypatch, *, payload=None):
    root = tmp_path / "invented-publication";root.mkdir(mode=0o700)
    output = module.original.capture.custody._Directory(root)
    context = _context();summary = _summary()
    if payload is None:
        payload = {"schema": pure.SCHEMA, "profile": pure.PROFILE, "fixture_only": True,
            "period": "2006Q1", **{key: summary[key] for key in ("counts", "title_refusal_counts", "ticker_refusal_counts", "authority")}}
    encoded = module._raw(payload)
    reservation = module._raw(module._reservation(summary["audit_id"], context))
    execution = {"invented_executed_image": True}
    monkeypatch.setattr(module, "_source_execution_context", lambda *_: execution)
    complete = {"schema": module.SCHEMA + "/complete", "audit_id": summary["audit_id"], "fixture_only": True,
        "observed_at_utc": "2026-10-14T00:00:00+00:00", "current_execution_identity": context["identity"],
        "frozen_sources": context["frozen_sources"], "source_view_context": context["source_view_context"],
        "sharadar_context": context["sharadar_context"], "reservation_sha256": module._sha(reservation),
        "assessment_sha256": module._sha(encoded), "assessment_bytes": len(encoded),
        **{key: summary[key] for key in ("counts", "title_refusal_counts", "ticker_refusal_counts", "authority")},
        "source_execution": {"executed_sources": []}, "source_only_bootstrap_sha256": module._sha(module.SOURCE_ONLY_BOOTSTRAP.encode())}
    complete["source_execution"] = {**execution, "executed_sources": []}
    monkeypatch.setattr(module, "_source_execution_context", lambda *_: complete["source_execution"])
    output.publish("reservation.json", reservation)
    output.publish("assessment.json", encoded)
    summary["assessment_sha256"] = complete["assessment_sha256"]
    complete_raw = module._raw(complete);output.publish("complete.json", complete_raw)
    summary["complete_sha256"] = module._sha(complete_raw)
    return output,context,summary,encoded


@pytest.mark.parametrize("kind", ["wrong_period", "no_roster", "wrong_population_context", "positive_semantic_authority"])
def test_parent_readback_cannot_accept_self_reported_coherently_rehashed_payload_without_input_rederivation(tmp_path, monkeypatch, kind):
    payload = {"schema": pure.SCHEMA, "profile": pure.PROFILE, "fixture_only": True, "period": "2006Q1",
        **{key: _summary()[key] for key in ("counts", "title_refusal_counts", "ticker_refusal_counts", "authority")}}
    if kind == "wrong_period":payload["period"] = "2022Q4"
    elif kind == "wrong_population_context":payload["source_cohort_binding"] = {"ordered_source_row_identity_sha256": "f" * 64}
    elif kind == "positive_semantic_authority":payload["financial_fields_interpreted_or_projected"] = True
    output,context,summary,_ = _write_publication(tmp_path, monkeypatch, payload=payload)
    try:
        with pytest.raises(ValueError):module._verify_publication(output, summary, context=context, fixture_only=True)
    finally:output.close()


@pytest.mark.parametrize("root", [LANE, LANE.parent, LANE.parent / "other-lane"])
def test_fixture_fence_precedes_actual_root_callbacks(root, monkeypatch):
    monkeypatch.setattr(module.original.capture, "_fixture_root", lambda *_: pytest.fail("actual-root callback reached"))
    monkeypatch.setattr(module.original.capture.bootstrap, "_Tree", lambda *_: pytest.fail("actual tree reached"))
    with pytest.raises(ValueError):module._PinnedSourceView(fixture_only=True, root=root, leaf_pins={})


def test_inactive_actual_cli_is_refused_before_source_or_input_callbacks(monkeypatch, capsys):
    monkeypatch.setattr(module, "__file__", str(DIR / "deliberately-inactive-front.py"))
    monkeypatch.setattr(module.original, "_fixed_source_identity", lambda *_: pytest.fail("actual identity reached"))
    monkeypatch.setattr(module, "_PinnedSourceView", lambda *_: pytest.fail("actual input reached"))
    assert module.main(["--audit-id", "ib-sec-title-current-reference-invented", "--expected-head", "a" * 40]) == 2
    diagnostic = json.loads(capsys.readouterr().out)
    assert diagnostic["failure_phase"] == "parent_preflight"
    assert set(diagnostic) == {"disposition", "failure_phase", "failure_class", "os_errno"}


def test_external_input_failure_precedes_any_fresh_reservation(monkeypatch):
    monkeypatch.setattr(module, "_fixed_source_identity", lambda *_: ({}, {}))
    monkeypatch.setattr(module.original.capture, "_verify_original_committed_sources", lambda *_: None)
    def refuse():raise ValueError("invented_source_refusal")
    monkeypatch.setattr(module, "_PinnedSourceView", refuse)
    monkeypatch.setattr(module, "_output_directory", lambda *_args, **_kwargs: pytest.fail("premature fresh reservation"))
    with pytest.raises(ValueError):module.run_observed_assessment("ib-sec-title-current-reference-invented", expected_head="a" * 40)


def _genuine_context(arguments):
    source = json.loads(arguments["source_view_assessment_raw"])
    return {"identity": {"head": "a" * 40, "source_sha256": {}}, "frozen_sources": {},
        "source_view_context": {"counts": source["counts"], "held_original_context": json.loads(arguments["source_view_complete_raw"])["frozen_original_baseline"]},
        "sharadar_context": {"counts": json.loads(arguments["sharadar_complete_raw"])["counts"]}}


def _genuine_publication(tmp_path, supplied, monkeypatch):
    arguments = fixtures.arguments(supplied, issuer_first=True)
    result = pure.assess_sec_title_current_reference(**arguments)
    context = _genuine_context(arguments);audit = "ib-sec-title-current-reference-invented"
    root = tmp_path / "genuine-output";root.mkdir(mode=0o700)
    output = module.original.capture.custody._Directory(root)
    execution = {"executed_sources": [], "invented_source_execution_context": True}
    monkeypatch.setattr(module, "_source_execution_context", lambda *_: execution)
    reservation = module._raw(module._reservation(audit, context));output.publish("reservation.json", reservation)
    summary = module._publish(output, result, audit_id=audit, context=context,
        reservation_raw=reservation, executed_sources=[], fixture_only=True)
    return output,context,summary,result.canonical_bytes()


def test_genuine_six_form_reference_publication_roundtrip_is_rederived_before_acceptance(tmp_path, supplied, monkeypatch):
    output,context,summary,expected = _genuine_publication(tmp_path, supplied, monkeypatch)
    try:
        complete = module._verify_publication(output, summary, context=context, expected_assessment_raw=expected, fixture_only=True)
        assert complete["counts"]["source_filings"] == 6 and complete["counts"]["parser_refused_selected_parents"] == 1
        assert summary["counts"]["ticker_rows"] == 4
        assert len(json.loads(expected)["filing_roster"]) == 6
        assert set(os.listdir(output.fd)) == module._FILES
    finally:output.close()


@pytest.mark.parametrize("kind", ["period", "source_context", "roster_accession", "roster_order", "title_text", "title_path",
    "group_cik", "group_rows", "ticker_row_hash", "parent_disposition", "semantic_authority", "counts"])
def test_input_rederived_readback_rejects_coherently_rehashed_real_shape_payload(tmp_path, supplied, monkeypatch, kind):
    output,context,summary,expected = _genuine_publication(tmp_path, supplied, monkeypatch)
    try:
        body = json.loads(expected)
        if kind == "period":body["period"] = "2022Q4"
        elif kind == "source_context":body["source_cohort_binding"]["ordered_source_row_identity_sha256"] = "f" * 64
        elif kind == "roster_accession":body["filing_roster"][0]["accession_number"] = "9999999999-06-999999"
        elif kind == "roster_order":body["filing_roster"] = list(reversed(body["filing_roster"]))
        elif kind == "title_text":body["title_occurrences"][0]["declared_title_decoded_text"] = "Other Class"
        elif kind == "title_path":body["title_occurrences"][0]["xml_occurrence_path"] = "/ownershipDocument/derivativeTable[1]"
        elif kind == "group_cik":body["current_permaticker_groups"][0]["current_cik_candidates"] = ["0000999999"]
        elif kind == "group_rows":body["current_permaticker_groups"][0]["ticker_source_ordinals"] = [3,4]
        elif kind == "ticker_row_hash":body["ticker_row_dispositions"][0]["source_row_sha256"] = "f" * 64
        elif kind == "parent_disposition":body["parent_title_dispositions"][1]["source_parent_disposition"] = "source_view_projected_noncanonical"
        elif kind == "semantic_authority":body["actions_read_or_interpreted"] = True
        else:body["counts"]["plain_title_occurrences"] = 0;body["counts"]["quarantined_title_occurrences"] = 1
        body["filing_roster_sha256"] = module._sha(module._raw(body["filing_roster"]))
        mutated = module._raw(body)
        (output.path / "assessment.json").write_bytes(mutated)
        complete = json.loads(output.read("complete.json", cap=module.MAX_CONTROL_BYTES))
        complete["assessment_sha256"] = summary["assessment_sha256"] = module._sha(mutated)
        complete["assessment_bytes"] = len(mutated)
        for key in ("counts", "title_refusal_counts", "ticker_refusal_counts", "authority"):
            complete[key] = summary[key] = body[key]
        mutated_complete = module._raw(complete);(output.path / "complete.json").write_bytes(mutated_complete)
        summary["complete_sha256"] = module._sha(mutated_complete)
        with pytest.raises(ValueError):module._verify_publication(output, summary, context=context,
            expected_assessment_raw=expected, fixture_only=True)
    finally:output.close()


def test_valid_summary_control_is_input_bound():
    body = _summary()
    assert module._validate_summary(body, audit_id=body["audit_id"], context=_context(), fixture_only=True) is body


@pytest.mark.parametrize("kind", ["parent_phase", "private_field", "unknown_class", "bool_errno", "stderr", "missing_lf", "double_lf", "wrong_return"])
def test_child_failure_cannot_publish_private_values_or_parent_phase(tmp_path, kind):
    root = tmp_path / "failed-child";root.mkdir(mode=0o700)
    output = module.original.capture.custody._Directory(root)
    output.publish("reservation.json", b"{}")
    diagnostic = module._failure_diagnostic(ValueError("SECRET PRIVATE SOURCE"), "worker_inputs")
    if kind == "parent_phase":diagnostic["failure_phase"] = "parent_inputs"
    elif kind == "private_field":diagnostic["private_source"] = "SECRET"
    elif kind == "unknown_class":diagnostic["failure_class"] = "SECRET"
    elif kind == "bool_errno":diagnostic["os_errno"] = True
    stdout = module._raw(diagnostic) + b"\n"
    if kind == "missing_lf":stdout = stdout[:-1]
    elif kind == "double_lf":stdout += b"\n"
    child = SimpleNamespace(returncode=1 if kind == "wrong_return" else 2, stdout=stdout,
        stderr=b"SECRET" if kind == "stderr" else b"")
    try:
        with pytest.raises(ValueError):module._raise_reported_worker_failure(child, output,
            audit_id="ib-sec-title-current-reference-invented", stage="readonly_semantic_verification")
        assert set(os.listdir(output.fd)) == {"reservation.json"}
    finally:output.close()


def test_structured_worker_refusal_is_retained_once_and_never_success(tmp_path):
    root = tmp_path / "failed-child-control";root.mkdir(mode=0o700)
    output = module.original.capture.custody._Directory(root);output.publish("reservation.json", b"{}")
    diagnostic = module._failure_diagnostic(OSError(13, "SECRET PATH"), "worker_inputs")
    child = SimpleNamespace(returncode=2, stdout=module._raw(diagnostic) + b"\n", stderr=b"")
    try:
        with pytest.raises(module.ReportedCurrentReferenceWorkerError) as caught:
            module._raise_reported_worker_failure(child, output, audit_id="ib-sec-title-current-reference-invented", stage="composition")
        assert module._failure_diagnostic(caught.value) == diagnostic
        body = output.read("worker-failure.json", cap=module.MAX_CONTROL_BYTES)
        assert b"SECRET" not in body and json.loads(body)["stage"] == "composition"
        caught.value.diagnostic["private"] = "SECRET"
        assert b"SECRET" not in module._raw(module._failure_diagnostic(caught.value))
        assert set(os.listdir(output.fd)) == {"reservation.json", "worker-failure.json"}
    finally:output.close()


def test_readonly_verifier_requires_native_isolation_before_any_input_read(monkeypatch, tmp_path):
    output = SimpleNamespace(fd=-1, path=tmp_path, read=lambda *_args, **_kwargs: module._raw(module._reservation("ib-sec-title-current-reference-invented", _context())), close=lambda: None)
    monkeypatch.setattr(module, "__file__", str(LANE / module.SELF_PATH))
    monkeypatch.setattr(module.original.capture.bootstrap, "_required_identity", lambda *_: None)
    monkeypatch.setattr(module, "_current_bytes", lambda *_: None)
    monkeypatch.setattr(module, "_output_directory", lambda *_args, **_kwargs: output)
    monkeypatch.setattr(module.os, "listdir", lambda *_: module._FILES)
    def refuse(_):raise ValueError("invented_native_denial_not_proven")
    monkeypatch.setattr(module.original, "_prove_worker_isolation", refuse)
    monkeypatch.setattr(module.sys, "addaudithook", lambda *_: pytest.fail("hook installed before native proof"))
    monkeypatch.setattr(module, "_PinnedSourceView", lambda: pytest.fail("source input before native proof"))
    with pytest.raises(ValueError, match="invented_native_denial_not_proven"):
        module._worker("ib-sec-title-current-reference-invented", expected_head="a" * 40,
            context=_context(), executed_sources=[], bootstrap_source={}, verify_only=True)


def test_readonly_policy_has_process_tree_network_and_all_write_denial(tmp_path):
    policy = module.original.isolation._worker_policy(tmp_path, readonly=True)
    assert "(deny network*)" in policy and "(deny process-fork)" in policy and "(deny process-exec)" in policy
    assert "(deny file-write*)" in policy and "(allow file-write*" not in policy


def _retained_descriptors(supplied):
    descriptors = []
    table = b"<nonDerivativeTable>" + fixtures._row() + b"</nonDerivativeTable>"
    for item in fixtures.source_fixture._inputs(supplied, 2):
        inner = fixtures.source_fixture._inner(item["request"]).replace(b"</ownershipDocument>", table + b"</ownershipDocument>")
        descriptors.append(fixtures.source_fixture._with_raw(item, fixtures.source_fixture._wrap(inner)))
    return tuple(descriptors)


def test_recreated_parent_inventory_rejects_boolean_prefix_even_when_equal_to_zero(supplied):
    args = fixtures.arguments(supplied)
    descriptors = list(_retained_descriptors(supplied));descriptors[0] = {**descriptors[0], "prefix_ordinal": False}
    with pytest.raises(ValueError):module._recreate_inventory(tuple(descriptors), json.loads(args["source_view_assessment_raw"]), fixture_only=True)


def test_recreated_inventory_control_uses_original_bodies_not_saved_projection(supplied):
    args = fixtures.arguments(supplied)
    inventory = module._recreate_inventory(_retained_descriptors(supplied), json.loads(args["source_view_assessment_raw"]), fixture_only=True)
    assert inventory.sha256 == args["source_view_parent_inventory"].sha256


@pytest.mark.parametrize("kind", ["stderr", "missing_lf", "two_lf", "whitespace", "duplicate_key", "return_bool", "too_large"])
def test_child_success_is_one_bounded_canonical_json_line_without_private_stderr(kind):
    child = SimpleNamespace(returncode=0, stdout=b'{"summary":true}\n', stderr=b"")
    if kind == "stderr":child.stderr = b"SECRET"
    elif kind == "missing_lf":child.stdout = child.stdout[:-1]
    elif kind == "two_lf":child.stdout += b"\n"
    elif kind == "whitespace":child.stdout = b'{ "summary":true}\n'
    elif kind == "duplicate_key":child.stdout = b'{"summary":false,"summary":true}\n'
    elif kind == "return_bool":child.returncode = False
    else:child.stdout = b"x" * (module.MAX_CONTROL_BYTES + 1)
    with pytest.raises(ValueError):module._child_json(child)


def test_child_success_canonical_control():
    assert module._child_json(SimpleNamespace(returncode=0, stdout=b'{"summary":true}\n', stderr=b"")) == {"summary": True}


def test_readonly_isolation_probe_explicitly_checks_inside_output_write(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(module.original, "_prove_worker_isolation", lambda path: calls.append(("outside_network_fork", path)))
    def denied(path, flags, mode):
        calls.append(("inside_output", path))
        raise OSError(13, "private path must not be printed")
    monkeypatch.setattr(module.os, "open", denied)
    module._prove_readonly_isolation(tmp_path)
    assert calls == [("outside_network_fork", tmp_path), ("inside_output", tmp_path / ".readonly-write-probe")]


def _source_view_root(tmp_path, supplied):
    preceding = module.view_front
    root = tmp_path / "held-view-input";root.mkdir(mode=0o700)
    output = module.original.capture.custody._Directory(root)
    baseline = preceding_fixtures._invented_baseline(supplied)
    identity = preceding_fixtures._identity();audit_id = module.VIEW_ID
    reservation = preceding._raw(preceding._reservation(audit_id, identity, {}, preceding.CAPTURE_REPORT, baseline))
    output.publish("reservation.json", reservation)
    bootstrap = {"path": "research/insider_buying_affected_quarter_isolation.py", "sha256": "a" * 64}
    rows = [{"path": name, "sha256": digest} for name,digest in identity["source_sha256"].items() if name != bootstrap["path"]]
    try:
        preceding._publish_assessment(output, preceding_fixtures._result(supplied), audit_id=audit_id,
            reservation_raw=reservation, identity=identity, frozen={}, baseline=baseline,
            capture_reservation={"execution_identity": {"source_inventory_sha256": "c" * 64}},
            capture_report={"capture_execution_head": "d" * 40, "bootstrap_execution_head": "e" * 40},
            executed_sources=rows, bootstrap_source=bootstrap, fixture_only=True)
        pins = {name: (module._sha(output.read(name, cap=module.MAX_INPUT_BYTES)), (root / name).stat().st_size)
            for name in module.VIEW_LEAVES}
    finally:output.close()
    return root,pins,baseline


def test_pinned_view_context_full_source_roster_and_all_five_leaf_rechecks(tmp_path, supplied):
    root,pins,baseline = _source_view_root(tmp_path, supplied)
    held = module._PinnedSourceView(fixture_only=True, root=root, leaf_pins=pins, baseline_context=baseline)
    try:
        held.recheck()
        assert held.context["full_ordered_source_identity"] == baseline["preparation_context"]
        assert held.context["counts"]["source_filings"] == 6
        (root / "parent-ledger.json").write_bytes(b"{}")
        with pytest.raises(ValueError):held.recheck()
    finally:held.close()


@pytest.mark.parametrize("kind", ["external_hash", "extra_leaf", "leaf_mode", "hardlink", "substitution", "reordered_roster", "source_lineage"])
def test_pinned_view_refuses_custody_or_rehashed_source_roster_and_producer_changes(tmp_path, supplied, kind):
    root,pins,baseline = _source_view_root(tmp_path, supplied)
    if kind == "external_hash":pins["assessment.json"] = ("f" * 64, pins["assessment.json"][1])
    elif kind == "extra_leaf":(root / "extra.json").write_bytes(b"{}");(root / "extra.json").chmod(0o600)
    elif kind == "leaf_mode":(root / "assessment.json").chmod(0o644)
    elif kind == "hardlink":os.link(root / "assessment.json", tmp_path / "leaked-assessment")
    elif kind == "substitution":(root / "assessment.json").rename(tmp_path / "other-assessment");(root / "assessment.json").symlink_to(tmp_path / "other-assessment")
    else:
        complete = json.loads((root / "complete.json").read_bytes())
        if kind == "source_lineage":complete["bootstrap_execution_head"] = "f" * 40
        else:
            assessment = json.loads((root / "assessment.json").read_bytes())
            assessment["rows"] = list(reversed(assessment["rows"]))
            assessment["rows_sha256"] = module._sha(module._raw(assessment["rows"]))
            raw = module._raw(assessment);(root / "assessment.json").write_bytes(raw)
            pins["assessment.json"] = (module._sha(raw), len(raw))
            complete["assessment_sha256"] = module._sha(raw);complete["assessment_bytes"] = len(raw)
        raw = module._raw(complete);(root / "complete.json").write_bytes(raw);pins["complete.json"] = (module._sha(raw), len(raw))
    with pytest.raises((ValueError, OSError)):
        module._PinnedSourceView(fixture_only=True, root=root, leaf_pins=pins, baseline_context=baseline)


def _sharadar_root(tmp_path, supplied, *, mutate=None):
    args = fixtures.arguments(supplied)
    root = tmp_path / "held-current-reference";root.mkdir(mode=0o700)
    capture = tmp_path / "supplied-capture";capture.mkdir(mode=0o700)
    manifest = args["capture_manifest_raw"];manifest_sha = module._sha(manifest)
    controls = {"manifest.json": manifest, "manifest.sha256": (manifest_sha + "\n").encode()}
    for name in module.sharadar.supplied.FILES:controls[name] = b"not-read-not-decoded"
    for name,raw in controls.items():(capture / name).write_bytes(raw);(capture / name).chmod(0o600)
    leaves = {"tickers_projection.json": args["tickers_projection_raw"], "actions_projection.json": b"not-json-and-not-decoded",
        "assessment.json": b"not-json-and-not-decoded"}
    complete = json.loads(args["sharadar_complete_raw"])
    complete.update(dict.fromkeys(module.sharadar.FALSE_FLAGS, False))
    complete.update(audit_id=module.SHARADAR_ID, execution_identity={"head": "a" * 40},
        looks_jobs_backtests=[0,0,0], inventory_sha256="b" * 64, census_complete_sha256="c" * 64,
        actions_projection_sha256=module._sha(leaves["actions_projection.json"]), assessment_sha256=module._sha(leaves["assessment.json"]),
        assessment_bytes=len(leaves["assessment.json"]))
    if mutate is not None:mutate(complete)
    leaves["complete.json"] = module._raw(complete)
    for name,raw in leaves.items():(root / name).write_bytes(raw);(root / name).chmod(0o600)
    pins = {name: (module._sha(raw), len(raw)) for name,raw in leaves.items()}
    return root,capture,pins,(manifest_sha,len(manifest))


def test_pinned_reference_reads_tickers_controls_only_and_hashes_opaque_actions(tmp_path, supplied):
    root,capture,pins,manifest_pin = _sharadar_root(tmp_path, supplied)
    held = module._PinnedSharadar(fixture_only=True, root=root, capture_root=capture, leaf_pins=pins, manifest_pin=manifest_pin)
    try:
        assert set(held.raw) == {"tickers_projection.json", "complete.json"}
        assert {name for name,*_ in held.capture.handles} == {"manifest.json", "manifest.sha256"}
        held.recheck()
        (root / "actions_projection.json").write_bytes(b"not-json-and-now-changed")
        with pytest.raises(ValueError):held.recheck()
    finally:held.close()


@pytest.mark.parametrize("kind", ["bool_look", "positive_authority", "wrong_projection", "sidecar", "extra_file", "control_mutation"])
def test_pinned_reference_refuses_rehashed_scope_or_custody_changes(tmp_path, supplied, kind):
    def mutation(body):
        if kind == "bool_look":body["looks_jobs_backtests"] = [False,False,False]
        elif kind == "positive_authority":body["backtesting_ready"] = True
        elif kind == "wrong_projection":body["tickers_projection_sha256"] = "f" * 64
    root,capture,pins,manifest_pin = _sharadar_root(tmp_path, supplied, mutate=mutation)
    if kind == "sidecar":(capture / "manifest.sha256").write_bytes(b"f" * 64 + b"\n")
    elif kind == "extra_file":(root / "extra").write_bytes(b"x");(root / "extra").chmod(0o600)
    if kind != "control_mutation":
        with pytest.raises((ValueError, OSError)):module._PinnedSharadar(fixture_only=True, root=root, capture_root=capture,
            leaf_pins=pins, manifest_pin=manifest_pin)
    else:
        held = module._PinnedSharadar(fixture_only=True, root=root, capture_root=capture, leaf_pins=pins, manifest_pin=manifest_pin)
        try:
            (capture / "manifest.json").write_bytes(b"x" * manifest_pin[1])
            with pytest.raises(ValueError):held.recheck()
        finally:held.close()


def _bootstrap_envelope(*, verify_only=False, fail=False):
    helper_path = "research/insider_buying_affected_quarter_isolation.py"
    helper = (LANE / helper_path).read_bytes()
    consumer = b'import json\ndef _raw(value):return json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode()\n'
    if fail:consumer += b'def _worker(*args,**kwargs):raise ValueError("SECRET INPUT PATH AND BODY")\n'
    else:consumer += b'def _worker(*args,**kwargs):return {"fixture_only":True,"verify_only":kwargs["verify_only"]}\n'
    rows = [{"path": path, "sha256": module._sha(raw), "source_b64": base64.b64encode(raw).decode()}
        for path,raw in ((helper_path,helper), (module.SELF_PATH,consumer))]
    return {"sources": rows, "context": {"identity": {"source_sha256": {row["path"]: row["sha256"] for row in rows}}},
        "audit_id": "ib-sec-title-current-reference-invented", "expected_head": "a" * 40, "verify_only": verify_only}


@pytest.mark.parametrize("verify_only", [False, True])
def test_captured_bootstrap_serves_only_held_consumer_bytes_and_exact_mode(verify_only):
    child = subprocess.run([sys.executable, "-I", "-S", "-B", "-c", module.SOURCE_ONLY_BOOTSTRAP],
        input=module._raw(_bootstrap_envelope(verify_only=verify_only)), capture_output=True,
        cwd=LANE, env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin"}, timeout=20)
    assert child.returncode == 0 and child.stderr == b""
    assert module._child_json(child) == {"fixture_only": True, "verify_only": verify_only}


@pytest.mark.parametrize("kind", ["source_hash", "extra_source", "mode_bool", "unknown_context", "consumer_exception"])
def test_captured_bootstrap_source_scope_and_failures_are_fixed_and_secret_safe(kind):
    envelope = _bootstrap_envelope(fail=kind == "consumer_exception")
    if kind == "source_hash":envelope["sources"][1]["sha256"] = "f" * 64
    elif kind == "extra_source":envelope["context"]["identity"]["source_sha256"]["research/unheld.py"] = "a" * 64
    elif kind == "mode_bool":envelope["verify_only"] = 1
    elif kind == "unknown_context":envelope["unexpected"] = "SECRET"
    child = subprocess.run([sys.executable, "-I", "-S", "-B", "-c", module.SOURCE_ONLY_BOOTSTRAP],
        input=module._raw(envelope), capture_output=True, cwd=LANE,
        env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin"}, timeout=20)
    assert child.returncode == 2 and child.stderr == b"" and b"SECRET" not in child.stdout
    diagnostic = module._strict_failure(json.loads(child.stdout))
    assert diagnostic["failure_phase"].startswith("worker_")


@pytest.mark.parametrize("kind", ["wrong_hash", "missing_front", "unknown_path", "duplicate", "positive_reconstruction"])
def test_executed_source_context_is_bound_to_independent_current_inventory(kind):
    names = {module.SELF_PATH, module.PURE_PATH, module.view_front.SELF_PATH, module.view_front.PURE_PATH,
        module.view_front.VIEW_PATH, module.original.SELF_PATH, "research/insider_buying/sec_complete_submission.py",
        "research/insider_buying/sec_ib1c_identity_v2.py", "research/insider_buying_sharadar_reference_cohort.py"}
    identity = {"source_sha256": dict.fromkeys(names, "a" * 64)}
    rows = [{"path": path, "sha256": "a" * 64} for path in sorted(names)]
    if kind == "wrong_hash":rows[0]["sha256"] = "f" * 64
    elif kind == "missing_front":rows = [row for row in rows if row["path"] != module.SELF_PATH]
    elif kind == "unknown_path":rows.append({"path": "research/unheld.py", "sha256": "a" * 64})
    elif kind == "duplicate":rows.append(rows[0])
    else:
        body = module._source_execution_context(rows, identity)
        assert body["full_historical_environment_reconstructed"] is False
        return
    with pytest.raises(ValueError):module._source_execution_context(rows, identity)


@pytest.mark.parametrize("kind", ["same_bytes_replace", "content_change", "added_leaf", "linked_leaf"])
def test_final_output_versions_and_namespace_stay_held_across_last_source_checks(tmp_path, kind):
    root = tmp_path / "held-final-publication";root.mkdir(mode=0o700)
    expected = {}
    for name in module._FINAL_FILES:
        raw = module._raw({"invented_final_leaf": name})
        (root / name).write_bytes(raw);(root / name).chmod(0o600);expected[name] = module._sha(raw)
    held = module._PinnedPublication(root, expected, fixture_only=True)
    try:
        held.recheck()
        if kind == "same_bytes_replace":
            raw = (root / "complete.json").read_bytes();(root / "complete.json").rename(tmp_path / "old-complete")
            (root / "complete.json").write_bytes(raw);(root / "complete.json").chmod(0o600)
        elif kind == "content_change":(root / "readonly-verification.json").write_bytes(b"{}")
        elif kind == "added_leaf":(root / "secret-extra").write_bytes(b"{}")
        else:os.link(root / "assessment.json", tmp_path / "linked-assessment")
        with pytest.raises(ValueError):held.recheck()
    finally:held.close()
