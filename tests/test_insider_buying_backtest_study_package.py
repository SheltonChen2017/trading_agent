"""Invented trusted records only: no real approval, outcome rows or cloud run.

The production-branch controls simulate a trusted configuration service inside
tests; they are NOT evidence that these invented sources are SEC-authentic or
that any real account has licensed rights. No runtime safety guard is patched.
"""
import ast
from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest

from research.insider_buying import backtest_evidence_pipeline as pipeline
from research.insider_buying import backtest_study_package as module
from test_insider_buying_backtest_evidence_pipeline import make_pipeline_fixture


ROOT = Path(__file__).resolve().parents[1]
QC_SOURCE = ROOT / "research" / "insider_buying_qc_stock_order_study.py"


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _roots(scope, artifacts):
    # Fixture-only trusted-configuration simulator; never a production service.
    return module.StudyTrustRoots(scope, tuple((role, _sha(artifacts[role])) for role in module.ROLES))


def _bundle_inputs(*, scope="fixture", plan=False):
    kwargs = make_pipeline_fixture()
    if scope == "production":
        for role in ("source_manifest", "security_master", "calendar", "authorization"):
            obj = json.loads(kwargs[role]); obj["trust_scope"] = scope
            if role == "source_manifest":
                obj["origin"] = "sec-original-complete-submission"
            kwargs[role] = module.canonical_bytes(obj)
        auth = json.loads(kwargs["authorization"])
        auth["source_manifest_sha256"] = _sha(kwargs["source_manifest"])
        auth["security_master_sha256"] = _sha(kwargs["security_master"])
        kwargs["authorization"] = module.canonical_bytes(auth)
    kwargs["trust_roots"] = pipeline.EvidenceTrustRoots(scope, *(_sha(kwargs[role]) for role in (
        "source_manifest", "security_master", "calendar", "authorization")))
    first_result = pipeline.build_evidence_pipeline(**kwargs)
    manifest = json.loads(first_result.signal_manifest_bytes())
    sessions = manifest["sessions"]
    dataset, vintage = "invented-outcome-dataset", "invented-outcome-vintage"
    common = {"trust_scope": scope, "dataset_id": dataset, "vintage_id": vintage}
    delisting = {**common, "schema": "insider-backtest-delisting-v1", "semantics": "terminal-return-retained-no-survivor-drop"}
    adjustments = {**common, "schema": "insider-backtest-adjustments-v1", "price_normalization": "raw", "semantics": "split-dividend-events-retained"}
    outcome = {**common, "schema": "insider-backtest-outcome-header-v1",
               "source_manifest_sha256": manifest["source_manifest_sha256"],
               "security_master_sha256": manifest["security_master_sha256"],
               "calendar_sha256": manifest["calendar_sha256"], "first_session": sessions[0],
               "last_session": sessions[-1], "price_normalization": "raw",
               "delisting_sha256": _sha(module.canonical_bytes(delisting)),
               "adjustments_sha256": _sha(module.canonical_bytes(adjustments)),
               "coverage_signal_ids": sorted(row["signal_id"] for row in manifest["signals"]),
               "market_data_profile": module.qc_market_data_profile()}
    outcome_sha = _sha(module.canonical_bytes(outcome))
    rights_common = {**common, "account_id": "invented-account", "outcome_vintage_sha256": outcome_sha,
                     "representation": "local-and-quantconnect", "platform": "QuantConnect Cloud",
                     "first_session": sessions[0], "last_session": sessions[-1],
                     "market_data_profile": module.qc_market_data_profile(), "clock_data_entitlements": ["SPY"]}
    rights = {**rights_common, "schema": "insider-backtest-rights-v1", "use": module.SCOPE,
              "permissions": ["local-process", "qc-store", "qc-process"]}
    rights_sha = _sha(module.canonical_bytes(rights))
    entitlement = {**rights_common, "schema": "insider-backtest-qc-entitlement-v1",
                   "rights_record_sha256": rights_sha, "organization_id": "invented-organization", "job_type": "backtest"}
    protocol = {"schema": "insider-backtest-protocol-v1", "trust_scope": scope,
                "candidate_id": "invented-stock-candidate", "registered_look_id": "invented-study-1",
                "parent_gate_sha256": module.PARENT_GATE_SHA256,
                "primary_cell_id": "ib5-stock-open-market-purchase-20-session-v1",
                "primary_horizon_sessions": 20, "descriptive_horizons": [5, 60], "stock_alpha": [1, 160],
                "etf_alpha_reserve": [1, 160], "shared_cutoff": "2027-08-31", "holdout_start": "2027-09-01",
                "holdout_end": "2029-08-31", "valid_stock_null_closes_family": True,
                "etf_can_rescue_stock_null": False, "qc_can_rescue_stock_null": False,
                "analysis_plan": None if not plan else {
                    role: {"method_id": "invented-" + role, "definition": "fixture definition, not an approved statistical recipe",
                           "implementation_sha256": _sha(role.encode())}
                    for role in ("primary_statistic", "inference", "controls", "split", "error_policy")}}
    artifacts = {role: kwargs[role] for role in ("source_manifest", "security_master", "calendar")}
    artifacts.update({role: module.canonical_bytes(obj) for role, obj in (
        ("outcome", outcome), ("rights", rights), ("qc_entitlement", entitlement),
        ("delisting", delisting), ("adjustments", adjustments), ("protocol", protocol))})
    auth = json.loads(kwargs["authorization"])
    for field, role in (("outcome_vintage_sha256", "outcome"), ("rights_record_sha256", "rights"),
                        ("qc_entitlement_sha256", "qc_entitlement"), ("delisting_sha256", "delisting"),
                        ("adjustments_sha256", "adjustments"), ("protocol_sha256", "protocol")):
        auth[field] = _sha(artifacts[role])
    artifacts["authorization"] = kwargs["authorization"] = module.canonical_bytes(auth)
    kwargs["trust_roots"] = pipeline.EvidenceTrustRoots(scope, *(_sha(kwargs[role]) for role in (
        "source_manifest", "security_master", "calendar", "authorization")))
    result = pipeline.build_evidence_pipeline(**kwargs)
    assert [row["signal_id"] for row in result.signals()] == outcome["coverage_signal_ids"]
    return {"pipeline_result": result, "candidate_source": QC_SOURCE.read_bytes(),
            "evidence_artifacts": artifacts, "trust_roots": _roots(scope, artifacts)}


@pytest.fixture(scope="module")
def bundle_inputs():
    return _bundle_inputs()


@pytest.fixture(scope="module")
def package(bundle_inputs):
    return module.build_backtest_study_package(**bundle_inputs)


def _terminal(package, **updates):
    payload, files = package.to_payload(), package.files()
    manifest = json.loads(files["signals.json"])
    fills = [{"signal_id": row["signal_id"], "side": side, "qc_symbol_id": row["qc_symbol_id"],
              "session": row[side + "_session"], "quantity": 10 if side == "entry" else -10,
              "price": "100.00", "status": "Filled", "order_id": f"invented-order-{index}-{side}"}
             for index, row in enumerate(manifest["signals"]) for side in ("entry", "exit")]
    obj = {"schema": "insider-backtest-terminal-result-v1", "trust_scope": payload["trust_scope"],
           "package_sha256": package.sha256, "candidate_id": payload["candidate_id"],
           "registered_look_id": payload["registered_look_id"], "manifest_sha256": _sha(files["signals.json"]),
           "gate_sha256": _sha(files["gate.json"]), "candidate_source_sha256": _sha(files["main.py"]),
           "outcome_vintage_sha256": payload["artifact_sha256s"]["outcome"], "attempt_id": "attempt-1",
           "project_id": "invented-project", "compile_id": "invented-compile", "backtest_id": "invented-backtest",
           "status": "Completed", "errors": [], "processed_sessions": manifest["sessions"],
           "submitted_order_count": len(fills), "final_positions": [], "fills": fills}
    obj.update(updates)
    if obj["status"] == "CompileError" and "backtest_id" not in updates:
        obj["backtest_id"] = None
    return obj


def _analyze(package, obj):
    raw = module.canonical_bytes(obj)
    return module.analyze_terminal_result(package=package, raw=raw, expected_result_sha256=_sha(raw))


def test_genuine_admission_to_nonempty_fixture_bundle_is_content_bound_disabled_and_unadjudicated(package):
    payload, files = package.to_payload(), package.files()
    assert payload["signal_count"] == 20 and payload["input_bundle_verified"] is True
    assert payload["trust_scope"] == "fixture" and payload["production_input_bundle_verified"] is False
    assert payload["candidate_configured"] is True and payload["candidate_enabled"] is False
    assert payload["analysis_implementations_verified"] is False
    assert payload["outcome_rows_read"] == payload["qc_jobs_launched"] == 0
    assert payload["alpha_spent"] == [0, 1] and payload["statistical_gate"] == "UNADJUDICATED"
    assert b"RESEARCH_BACKTEST_ENABLED = False\n" in files["main.py"]
    assert all(_sha(raw) == payload["file_sha256s"][name] for name, raw in files.items())
    assert _analyze(package, _terminal(package))["order_path_verified"] is True
    assert _analyze(package, _terminal(package))["ib5_pass"] is False
    with pytest.raises(module.StudyPackageError):
        module.configure_registered_qc_candidate(package)


@pytest.mark.parametrize("role", module.ROLES)
def test_role_byte_drift_is_rejected_before_content_claims(bundle_inputs, role):
    artifacts = {**bundle_inputs["evidence_artifacts"], role: bundle_inputs["evidence_artifacts"][role] + b" "}
    with pytest.raises(module.StudyPackageError, match="external artifact hash"):
        module.build_backtest_study_package(**{**bundle_inputs, "evidence_artifacts": artifacts})


@pytest.mark.parametrize("role,edit", [
    ("outcome", lambda b: b.update(vintage_id="another-vintage")),
    ("outcome", lambda b: b.update(price_normalization="adjusted")),
    ("outcome", lambda b: b.update(coverage_signal_ids=[])),
    ("outcome", lambda b: b.update(last_session="2029-08-31")),
    ("outcome", lambda b: b["market_data_profile"].update(provider="local-vendor")),
    ("outcome", lambda b: b["market_data_profile"].update(stock_resolution="daily")),
    ("outcome", lambda b: b["market_data_profile"].update(stock_fill_forward=0)),
    ("outcome", lambda b: b["market_data_profile"].update(stock_price_normalization="adjusted")),
    ("outcome", lambda b: b.update(security_master_sha256="f" * 64)),
    ("rights", lambda b: b.update(permissions=["local-process"])),
    ("rights", lambda b: b.update(representation="local-only")),
    ("rights", lambda b: b.update(platform="Other Cloud")),
    ("rights", lambda b: b.update(use="paper-live")),
    ("rights", lambda b: b.update(clock_data_entitlements=[])),
    ("rights", lambda b: b["market_data_profile"].update(clock_extended_market_hours=False)),
    ("rights", lambda b: b.update(dataset_id="other-dataset")),
    ("rights", lambda b: b.update(last_session="2023-01-20")),
    ("qc_entitlement", lambda b: b.update(account_id="another-account")),
    ("qc_entitlement", lambda b: b.update(job_type="live")),
    ("qc_entitlement", lambda b: b.update(clock_data_entitlements=[])),
    ("qc_entitlement", lambda b: b["market_data_profile"].update(clock_fill_forward=True)),
    ("qc_entitlement", lambda b: b.update(rights_record_sha256="f" * 64)),
    ("delisting", lambda b: b.update(semantics="survivors-only")),
    ("adjustments", lambda b: b.update(price_normalization="adjusted")),
    ("protocol", lambda b: b.update(stock_alpha=[1, 80])),
    ("protocol", lambda b: b.update(primary_horizon_sessions=True)),
    ("protocol", lambda b: b.update(valid_stock_null_closes_family=1)),
    ("protocol", lambda b: b.update(etf_can_rescue_stock_null=True)),
    ("protocol", lambda b: b.update(qc_can_rescue_stock_null=0)),
    ("protocol", lambda b: b.update(analysis_plan={})),
    ("protocol", lambda b: b.update(registered_look_id="different-look")),
    ("calendar", lambda b: b["sessions"][4].update(close_utc="2023-01-20T00:00:00Z")),
    ("security_master", lambda b: b["mappings"][-1].update(knowledge_at_utc="2023-01-20T22:00:00Z")),
    ("authorization", lambda b: b.update(scope="live")),
    ("authorization", lambda b: b.update(protocol_sha256="f" * 64)),
])
def test_reanchored_fixture_contents_must_still_crossbind_subject_representation_policy_and_coverage(bundle_inputs, role, edit):
    artifacts = dict(bundle_inputs["evidence_artifacts"])
    obj = json.loads(artifacts[role]); edit(obj)
    artifacts[role] = module.canonical_bytes(obj)
    with pytest.raises(module.StudyPackageError):
        module.build_backtest_study_package(**{**bundle_inputs, "evidence_artifacts": artifacts, "trust_roots": _roots("fixture", artifacts)})


def _coherently_rebound_fixture_inputs(bundle_inputs, role, edit):
    """Regenerate ALL fixture crosshashes and the genuine pipeline, not a seal."""
    bodies = {name: json.loads(raw) for name, raw in bundle_inputs["evidence_artifacts"].items()}
    edit(bodies[role])
    bodies["outcome"]["delisting_sha256"] = _sha(module.canonical_bytes(bodies["delisting"]))
    bodies["outcome"]["adjustments_sha256"] = _sha(module.canonical_bytes(bodies["adjustments"]))
    outcome_sha = _sha(module.canonical_bytes(bodies["outcome"]))
    bodies["rights"]["outcome_vintage_sha256"] = outcome_sha
    bodies["qc_entitlement"]["outcome_vintage_sha256"] = outcome_sha
    bodies["qc_entitlement"]["rights_record_sha256"] = _sha(module.canonical_bytes(bodies["rights"]))
    for field, name in (("outcome_vintage_sha256", "outcome"), ("rights_record_sha256", "rights"),
                        ("qc_entitlement_sha256", "qc_entitlement"), ("delisting_sha256", "delisting"),
                        ("adjustments_sha256", "adjustments"), ("protocol_sha256", "protocol")):
        bodies["authorization"][field] = _sha(module.canonical_bytes(bodies[name]))
    artifacts = {name: module.canonical_bytes(body) for name, body in bodies.items()}
    kwargs = make_pipeline_fixture()
    for name in ("source_manifest", "security_master", "calendar", "authorization"):
        kwargs[name] = artifacts[name]
    kwargs["trust_roots"] = pipeline.EvidenceTrustRoots("fixture", *(_sha(kwargs[name]) for name in (
        "source_manifest", "security_master", "calendar", "authorization")))
    genuine = pipeline.build_evidence_pipeline(**kwargs)
    return {**bundle_inputs, "pipeline_result": genuine, "evidence_artifacts": artifacts,
            "trust_roots": _roots("fixture", artifacts)}


@pytest.mark.parametrize("role,edit", [
    ("outcome", lambda b: b.update(coverage_signal_ids=[])),
    ("outcome", lambda b: b.update(price_normalization="adjusted")),
    ("outcome", lambda b: b.update(last_session="2029-08-31")),
    ("rights", lambda b: b.update(permissions=["local-process"])),
    ("rights", lambda b: b.update(platform="Other Cloud")),
    ("rights", lambda b: b.update(use="paper-live")),
    ("qc_entitlement", lambda b: b.update(account_id="other-account")),
    ("qc_entitlement", lambda b: b.update(job_type="live")),
    ("delisting", lambda b: b.update(semantics="survivors-only")),
    ("adjustments", lambda b: b.update(semantics="events-dropped")),
    ("protocol", lambda b: b.update(stock_alpha=[1, 80])),
    ("protocol", lambda b: b.update(qc_can_rescue_stock_null=True)),
])
def test_fully_rehashed_coherent_fixture_still_cannot_replace_required_contents(bundle_inputs, role, edit):
    inputs = _coherently_rebound_fixture_inputs(bundle_inputs, role, edit)
    assert inputs["pipeline_result"].to_payload()["authorization_sha256"] == dict(inputs["trust_roots"].role_hashes)["authorization"]
    with pytest.raises(module.StudyPackageError):
        module.build_backtest_study_package(**inputs)


@pytest.mark.parametrize("role,edit", [
    ("outcome", lambda b: b["market_data_profile"].update(provider="local-vendor")),
    ("outcome", lambda b: b["market_data_profile"].update(stock_resolution="daily")),
    ("outcome", lambda b: b["market_data_profile"].update(stock_fill_forward=0)),
    ("outcome", lambda b: b["market_data_profile"].update(stock_price_normalization="adjusted")),
    ("rights", lambda b: b.update(clock_data_entitlements=[])),
    ("rights", lambda b: b["market_data_profile"].update(clock_extended_market_hours=False)),
    ("qc_entitlement", lambda b: b.update(clock_data_entitlements=[])),
    ("qc_entitlement", lambda b: b["market_data_profile"].update(clock_fill_forward=True)),
])
def test_fully_rehashed_native_feed_and_clock_claims_must_match_candidate(bundle_inputs, role, edit):
    inputs = _coherently_rebound_fixture_inputs(bundle_inputs, role, edit)
    with pytest.raises(module.StudyPackageError):
        module.build_backtest_study_package(**inputs)


@pytest.mark.parametrize("replacement", [None, {}, b"", "fake", 0])
def test_pipeline_declarations_cannot_bypass_factory_admission(bundle_inputs, replacement):
    with pytest.raises(pipeline.EvidencePipelineError):
        module.build_backtest_study_package(**{**bundle_inputs, "pipeline_result": replacement})


def test_artifact_scope_cannot_be_promoted_by_roots_only(bundle_inputs):
    with pytest.raises(module.StudyPackageError, match="trust scope"):
        module.build_backtest_study_package(**{**bundle_inputs, "trust_roots": _roots("production", bundle_inputs["evidence_artifacts"])})


def test_package_accessors_are_detached_reconstruction_and_mutation_refuse(package):
    payload = package.to_payload(); payload["candidate_enabled"] = True
    files = package.files(); files["main.py"] = b"different source"
    assert package.to_payload()["candidate_enabled"] is False
    assert package.files()["main.py"] != files["main.py"]
    with pytest.raises(module.StudyPackageError):
        replace(package).to_payload()
    altered = replace(package)
    object.__setattr__(altered, "_factory_sha256", package.sha256)
    object.__setattr__(altered, "_payload", b"{}")
    with pytest.raises(module.StudyPackageError):
        altered.files()


def test_direct_constructor_cannot_reseal_new_artifacts_as_a_verified_package(package):
    payload = package.to_payload(); payload["candidate_enabled"] = True
    encoded = module.canonical_bytes(payload)
    files = tuple(package.files().items())
    forged = module.BacktestStudyPackage(package._token, encoded, files)
    object.__setattr__(forged, "_factory_sha256", _sha(module.canonical_bytes({
        "payload": encoded.hex(), "files": [[name, raw.hex()] for name, raw in files]})))
    with pytest.raises(module.StudyPackageError):
        forged.to_payload()


def test_production_like_configured_package_binds_enabled_source_to_result_and_attempts():
    # Explicit simulated external service. This does not authenticate invented filings.
    disabled = module.build_backtest_study_package(**_bundle_inputs(scope="production", plan=True))
    configured = module.configure_registered_qc_candidate(disabled)
    assert configured.sha256 != disabled.sha256
    assert b"RESEARCH_BACKTEST_ENABLED = True\n" in configured.files()["main.py"]
    assert b"RESEARCH_BACKTEST_ENABLED = False\n" in disabled.files()["main.py"]
    assert configured.to_payload()["file_sha256s"]["main.py"] == _sha(configured.files()["main.py"])
    assert _analyze(configured, _terminal(configured))["order_path_verified"] is True
    wrong = _terminal(configured, candidate_source_sha256=_sha(disabled.files()["main.py"]))
    with pytest.raises(module.StudyPackageError, match="candidate_source"):
        _analyze(configured, wrong)
    ledger = module.new_attempt_ledger(candidate_id="invented-stock-candidate", registered_look_id="invented-study-1", trust_scope="production")
    with pytest.raises(module.StudyPackageError, match="configured package"):
        module.begin_attempt(ledger_raw=ledger, expected_ledger_sha256=_sha(ledger), package=disabled, attempt_id="attempt-1")
    pending = module.begin_attempt(ledger_raw=ledger, expected_ledger_sha256=_sha(ledger), package=configured, attempt_id="attempt-1")
    assert json.loads(pending)["attempts"][0]["source_sha256"] == _sha(configured.files()["main.py"])
    assert configured.to_payload()["analysis_implementations_verified"] is False


def test_production_like_missing_analysis_plan_cannot_enable():
    disabled = module.build_backtest_study_package(**_bundle_inputs(scope="production"))
    with pytest.raises(module.StudyPackageError, match="analysis plan"):
        module.configure_registered_qc_candidate(disabled)


@pytest.mark.parametrize("field", ["package_sha256", "candidate_id", "registered_look_id", "manifest_sha256", "gate_sha256", "candidate_source_sha256", "outcome_vintage_sha256", "trust_scope"])
def test_terminal_other_source_vintage_look_or_package_refuses(package, field):
    with pytest.raises(module.StudyPackageError, match="binding"):
        _analyze(package, _terminal(package, **{field: "other"}))


@pytest.mark.parametrize("updates", [
    {"status": "RuntimeError"}, {"status": "CompileError", "fills": []},
    {"status": "Cancelled"}, {"status": "Refused"}, {"errors": ["fixture error"]},
    {"fills": []}, {"processed_sessions": []}, {"final_positions": ["SID"]},
    {"submitted_order_count": 0},
])
def test_completed_or_failed_run_without_full_clean_order_path_is_invalid_data(package, updates):
    analysis = _analyze(package, _terminal(package, **updates))
    assert analysis["order_path_verified"] is False
    assert analysis["data_validity"] == "INVALID_DATA" and analysis["statistical_gate"] == "UNADJUDICATED"


@pytest.mark.parametrize("change", [
    {"side": []}, {"side": "unknown"}, {"signal_id": []}, {"quantity": True}, {"quantity": 0},
    {"price": "NaN"}, {"price": "Infinity"}, {"price": "0"}, {"price": 100.0},
    {"status": "PartiallyFilled"}, {"qc_symbol_id": "other-SID"}, {"session": "2029-08-31"},
])
def test_terminal_fill_schema_and_bad_financial_direction_fail_closed(package, change):
    obj = _terminal(package); obj["fills"][0].update(change)
    with pytest.raises(module.StudyPackageError):
        _analyze(package, obj)


def test_duplicate_order_id_is_not_two_orders(package):
    obj = _terminal(package)
    obj["fills"][1]["order_id"] = obj["fills"][0]["order_id"]
    with pytest.raises(module.StudyPackageError, match="duplicate terminal order"):
        _analyze(package, obj)


def test_matched_exit_quantity_required_even_if_completed(package):
    obj = _terminal(package); obj["fills"][1]["quantity"] = -9
    assert _analyze(package, obj)["order_path_verified"] is False


@pytest.mark.parametrize("bad", [True, -1, 40001, "4", 4.0])
def test_terminal_order_count_exact_type_and_bound(package, bad):
    with pytest.raises(module.StudyPackageError):
        _analyze(package, _terminal(package, submitted_order_count=bad))


def test_attempts_count_all_failures_block_pending_and_stop_after_three(package):
    payload = package.to_payload()
    ledger = module.new_attempt_ledger(candidate_id=payload["candidate_id"], registered_look_id=payload["registered_look_id"], trust_scope="fixture")
    for number, status in enumerate(("CompileError", "RuntimeError", "Cancelled"), 1):
        identity = f"attempt-{number}"
        ledger = module.begin_attempt(ledger_raw=ledger, expected_ledger_sha256=_sha(ledger), package=package, attempt_id=identity)
        with pytest.raises(module.StudyPackageError):
            module.begin_attempt(ledger_raw=ledger, expected_ledger_sha256=_sha(ledger), package=package, attempt_id="overlap")
        raw = module.canonical_bytes(_terminal(package, attempt_id=identity, status=status, fills=[]))
        ledger = module.finish_attempt(ledger_raw=ledger, expected_ledger_sha256=_sha(ledger), package=package,
                                       result_raw=raw, expected_result_sha256=_sha(raw))
    status = module.attempt_ledger_status(ledger)
    assert status["attempt_count"] == status["unsuccessful_count"] == 3
    assert status["can_begin_attempt"] is False and status["requires_mia"] is True
    with pytest.raises(module.StudyPackageError):
        module.begin_attempt(ledger_raw=ledger, expected_ledger_sha256=_sha(ledger), package=package, attempt_id="attempt-4")


def test_completed_order_path_closes_candidate_but_does_not_pass_statistics(package):
    payload = package.to_payload()
    ledger = module.new_attempt_ledger(candidate_id=payload["candidate_id"], registered_look_id=payload["registered_look_id"], trust_scope="fixture")
    ledger = module.begin_attempt(ledger_raw=ledger, expected_ledger_sha256=_sha(ledger), package=package, attempt_id="attempt-1")
    raw = module.canonical_bytes(_terminal(package))
    ledger = module.finish_attempt(ledger_raw=ledger, expected_ledger_sha256=_sha(ledger), package=package, result_raw=raw, expected_result_sha256=_sha(raw))
    status = module.attempt_ledger_status(ledger)
    assert status["candidate_completed"] is True and status["can_begin_attempt"] is False
    assert status["statistical_gate"] == "UNADJUDICATED"


def test_ledger_anchor_prevents_replacing_prior_attempts(package):
    ledger = module.new_attempt_ledger(candidate_id="invented-stock-candidate", registered_look_id="invented-study-1", trust_scope="fixture")
    with pytest.raises(module.StudyPackageError, match="anchor"):
        module.begin_attempt(ledger_raw=ledger, expected_ledger_sha256="f" * 64, package=package, attempt_id="attempt-1")


def test_compile_failure_counts_without_inventing_a_nonexistent_backtest_id(package):
    payload = package.to_payload()
    ledger = module.new_attempt_ledger(candidate_id=payload["candidate_id"], registered_look_id=payload["registered_look_id"], trust_scope="fixture")
    ledger = module.begin_attempt(ledger_raw=ledger, expected_ledger_sha256=_sha(ledger), package=package, attempt_id="attempt-1")
    raw = module.canonical_bytes(_terminal(package, status="CompileError", backtest_id=None, fills=[], submitted_order_count=0))
    finished = module.finish_attempt(ledger_raw=ledger, expected_ledger_sha256=_sha(ledger), package=package, result_raw=raw, expected_result_sha256=_sha(raw))
    assert module.attempt_ledger_status(finished)["unsuccessful_count"] == 1


def _standalone_parsers():
    # Extract only stdlib imports/schema contracts, NEVER import the QC entry.
    source = QC_SOURCE.read_bytes()
    assert _sha(source) == module.QC_CANDIDATE_SHA256
    tree = ast.parse(source)
    nodes = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "InsiderBuyingStockOrderStudy":
            break
        if isinstance(node, ast.ImportFrom) and node.module == "AlgorithmImports":
            continue
        nodes.append(node)
    namespace = {"__name__": "fixture_schema_extract"}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(QC_SOURCE), "exec", dont_inherit=True), namespace)
    return namespace


def test_byte_export_parity_with_captured_exact_qc_public_parsers(package):
    parsers = _standalone_parsers()
    files, payload = package.files(), package.to_payload()
    manifest = parsers["parse_study_manifest"](files["signals.json"], _sha(files["signals.json"]))
    gate = parsers["parse_study_gate"](files["gate.json"], _sha(files["gate.json"]), manifest, payload["registered_look_id"])
    assert manifest.raw_sha256 == _sha(files["signals.json"])
    assert gate.rights_record_sha256 == payload["artifact_sha256s"]["rights"]
    assert len(manifest.signals) == payload["signal_count"]


@pytest.mark.parametrize("edit", [
    lambda b: b.update(signals=[]), lambda b: b["signals"].reverse(),
    lambda b: b["signals"].append(b["signals"][0]),
    lambda b: b["signals"][0].update(exit_session=b["sessions"][1]),
    lambda b: b["signals"][0].update(available_at_utc="2029-08-31T00:00:00+00:00"),
    lambda b: b.update(calendar_sha256="f" * 64),
    lambda b: b.update(unexpected=True),
])
def test_manifest_refusal_parity_with_exact_qc_schema(package, edit):
    value = json.loads(package.files()["signals.json"]); edit(value)
    raw = module.canonical_bytes(value)
    with pytest.raises(module.StudyPackageError):
        module.verify_signal_manifest(raw)
    parsers = _standalone_parsers()
    with pytest.raises(parsers["StockStudyRefusal"]):
        parsers["parse_study_manifest"](raw, _sha(raw))


def test_package_source_has_no_access_or_qc_entry_imports():
    source = (ROOT / "research" / "insider_buying" / "backtest_study_package.py").read_bytes()
    tree = ast.parse(source)
    imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert not any(name and (name.startswith("AlgorithmImports") or name.endswith("insider_buying_qc_stock_order_study")) for name in imports)
    calls = [node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)]
    assert not set(calls) & {"read_bytes", "write_bytes", "open", "connect", "launch", "upload", "backtest"}
