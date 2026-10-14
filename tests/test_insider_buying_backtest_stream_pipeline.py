"""Versioned source-stream→stock→QC-package fixture integration, no real access."""
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
import json
from zoneinfo import ZoneInfo

import pytest

from data.hashing import canonical_json, hash_bytes
from research.insider_buying import backtest_stream_pipeline as module
from research.insider_buying import backtest_study_package as package
from research.insider_buying.backtest_source_stream import build_stream_source_evidence
from test_insider_buying_backtest_source_stream import make_stream_fixture, _specs, _record, _edit_manifest
from test_insider_buying_backtest_evidence_pipeline import make_pipeline_fixture
from test_insider_buying_backtest_study_package import _bundle_inputs, _terminal, _analyze


def enc(value):
    return canonical_json(value).encode("utf-8")


def roots(kwargs):
    return module.StreamEvidenceTrustRoots("fixture", *(hash_bytes(kwargs[k]) for k in (
        "source_manifest", "security_master", "calendar", "authorization", "common_equity_exceptions", "stock_context")))


def make_stream_pipeline_fixture(count=300, *, periods=("2023Q1",), decision="2023-02-24", title="Common Stock", future=False):
    kwargs = make_pipeline_fixture()
    calendar = json.loads(kwargs["calendar"])
    if len(periods) > 1:
        current = date(2022, 9, 1)
        days = []
        eastern = ZoneInfo("America/New_York")
        while len(days) < 200:
            if current.weekday() < 5:
                days.append({"session": current.isoformat(), **{name + "_utc": datetime.combine(current, datetime.min.time()).replace(
                    hour=9 if name == "open" else 16, minute=30 if name == "open" else 0, tzinfo=eastern).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                    for name in ("open", "close")}})
            current += timedelta(days=1)
        calendar["sessions"] = days
    sessions = calendar["sessions"]
    i = [row["session"] for row in sessions].index(decision)
    specifications = None
    if future:
        specifications = list(_specs(count=count))
        specifications[-1] = ("4/A", "2023-03-01", "123456", specifications[-1][3], "20230301101112")
        specifications = {"2023Q1": tuple(specifications)}
    stream, _ = make_stream_fixture(periods=periods, count=count, decision=decision,
                                    lookback=sessions[i - 30]["session"], title=title, specs_by_period=specifications)
    stream["decision_cutoff_utc"] = sessions[i]["close_utc"]
    evidence = build_stream_source_evidence(**stream)
    master = json.loads(kwargs["security_master"])
    if len(periods) > 1:
        for mapping in master["mappings"]:
            mapping["mapping_first_session"] = "2022-01-01"
            mapping["knowledge_at_utc"] = "2022-01-01T00:00:00Z"
    master["mappings"][0]["security_title"] = title
    exception = {k: master["mappings"][0][k] for k in (
        "issuer_cik", "qc_symbol_id", "security_title", "share_class", "security_class", "knowledge_at_utc")}
    exception.update(first_session=master["mappings"][0]["mapping_first_session"], last_session="2024-01-01")
    dictionary = {"schema": "insider-common-equity-exceptions-v2", "trust_scope": "fixture",
                  "exceptions": [] if title == "Common Stock" else [exception]}
    context = {"schema": "insider-stock-context-v2", "trust_scope": "fixture", "calendar_sha256": hash_bytes(enc(calendar)),
               "decision_session": decision, "rows": [{"qc_symbol_id": item["qc_symbol_id"], "history": [
                   {"session": day["session"], "raw_close_usd": "10", "volume_shares": "200000", "knowledge_at_utc": day["close_utc"]}
                   for day in sessions[i - 60:i]]} for item in master["mappings"]]}
    auth = json.loads(kwargs["authorization"])
    auth.update(decision_session=decision, source_manifest_sha256=hash_bytes(stream["population_manifest"]),
                security_master_sha256=hash_bytes(enc(master)),
                calendar_sha256=hash_bytes(json.dumps([row["session"] for row in sessions], separators=(",", ":")).encode()))
    result = dict(source_evidence=evidence, source_manifest=stream["population_manifest"], security_master=enc(master),
                  calendar=enc(calendar), authorization=enc(auth), common_equity_exceptions=enc(dictionary), stock_context=enc(context))
    result["trust_roots"] = roots(result)
    return result


def test_actual_stream_factory_to_scores_and_nonempty_manifest_over_old_parent_cap():
    kwargs = make_stream_pipeline_fixture()
    result = module.build_stream_stock_pipeline(**kwargs)
    body = result.to_payload()
    assert body["stream_corroborated_form4_count"] == body["source_submission_count"] == 300
    assert body["preceding_quarantined_count"] == 300
    assert body["admitted_event_count"] == 1 and body["signal_count"] == 1
    assert body["scored_stock_count"] == 20
    assert sum(row["structural_zero"] for row in result.scored_rows()) == 19
    assert body["context_eligibility_verified"] is True
    assert body["literal_first_open_after_each_acceptance"] is False
    assert body["complete_project_backtesting_readiness"] is False
    assert body["research_looks"] == body["qc_jobs"] == 0
    assert len(result.admitted_events()[0]["member_event_ids"]) == 300
    assert result.admitted_events()[0]["purchase_value_usd"] == "15000000"
    assert len(package.verify_signal_manifest(result.signal_manifest_bytes())["signals"]) == 1


def test_crossquarter_source_window_integrates_without_invented_missing_history():
    kwargs = make_stream_pipeline_fixture(2, periods=("2022Q4", "2023Q1"), decision="2023-01-20")
    result = module.build_stream_stock_pipeline(**kwargs)
    assert result.to_payload()["source_window_start"] == "2022-10-01"
    assert result.to_payload()["score_lookback_start_session"] < "2023-01-01"
    assert len(result.admitted_events()) == 2
    assert result.to_payload()["signal_count"] == 1


def test_new_ordinary_classification_uses_exact_external_exception_without_thaw():
    result = module.build_stream_stock_pipeline(**make_stream_pipeline_fixture(3, title="Class A Ordinary Shares"))
    assert result.to_payload()["ordinary_share_exception_count"] == 3
    assert result.to_payload()["admitted_event_count"] == 1


def test_future_amendment_does_not_retroactively_remove_known_original_signal():
    result = module.build_stream_stock_pipeline(**make_stream_pipeline_fixture(3, future=True))
    assert result.to_payload()["future_parent_count"] == 1
    assert result.to_payload()["admitted_event_count"] == 1
    assert result.admitted_events()[0]["purchase_value_usd"] == "100000"


@pytest.mark.parametrize("role", ["source_manifest", "security_master", "calendar", "authorization", "common_equity_exceptions", "stock_context"])
def test_each_external_root_has_actual_byte_guard(role):
    kwargs = make_stream_pipeline_fixture(2)
    with pytest.raises(ValueError):
        module.build_stream_stock_pipeline(**{**kwargs, role: kwargs[role] + b" "})


@pytest.mark.parametrize("role,edit", [
    ("authorization", lambda b: b.update(decision_session="2023-02-23")),
    ("authorization", lambda b: b.update(source_manifest_sha256="0" * 64)),
    ("stock_context", lambda b: b["rows"].pop()),
    ("stock_context", lambda b: b["rows"][0]["history"][0].update(knowledge_at_utc="2024-01-01T00:00:00Z")),
    ("stock_context", lambda b: b["rows"][0]["history"][-1].update(raw_close_usd="4")),
    ("common_equity_exceptions", lambda b: b["exceptions"].clear()),
    ("common_equity_exceptions", lambda b: b["exceptions"][0].update(knowledge_at_utc="2024-01-01T00:00:00Z")),
    ("security_master", lambda b: b["mappings"][0].update(knowledge_at_utc="2024-01-01T00:00:00Z")),
])
def test_reanchored_contents_cannot_erase_required_economic_checks(role, edit):
    kwargs = make_stream_pipeline_fixture(2, title="Ordinary Shares")
    body = json.loads(kwargs[role]); edit(body)
    kwargs[role] = enc(body)
    kwargs["trust_roots"] = roots(kwargs)
    with pytest.raises(ValueError):
        module.build_stream_stock_pipeline(**kwargs)


def test_direct_reconstructed_stream_pipeline_cannot_reach_package():
    result = module.build_stream_stock_pipeline(**make_stream_pipeline_fixture(2))
    copy = replace(result)
    with pytest.raises(ValueError, match="reconstructed"):
        module.validate_stream_stock_pipeline(copy)


def make_stream_package_fixture(count=300):
    kwargs = make_stream_pipeline_fixture(count)
    old = _bundle_inputs()
    artifacts = dict(old["evidence_artifacts"])
    for role in ("source_manifest", "security_master", "calendar", "common_equity_exceptions", "stock_context"):
        artifacts[role] = kwargs[role]
    initial = module.build_stream_stock_pipeline(**kwargs)
    manifest = json.loads(initial.signal_manifest_bytes())
    outcome = json.loads(artifacts["outcome"])
    outcome.update(source_manifest_sha256=hash_bytes(artifacts["source_manifest"]),
                   security_master_sha256=hash_bytes(artifacts["security_master"]),
                   coverage_signal_ids=sorted(row["signal_id"] for row in manifest["signals"]))
    artifacts["outcome"] = enc(outcome)
    rights = json.loads(artifacts["rights"]); rights["outcome_vintage_sha256"] = hash_bytes(artifacts["outcome"])
    artifacts["rights"] = enc(rights)
    entitlement = json.loads(artifacts["qc_entitlement"])
    entitlement.update(outcome_vintage_sha256=hash_bytes(artifacts["outcome"]), rights_record_sha256=hash_bytes(artifacts["rights"]))
    artifacts["qc_entitlement"] = enc(entitlement)
    auth = json.loads(kwargs["authorization"])
    for field, role in (("outcome_vintage_sha256", "outcome"), ("rights_record_sha256", "rights"), ("qc_entitlement_sha256", "qc_entitlement"),
                        ("delisting_sha256", "delisting"), ("adjustments_sha256", "adjustments"), ("protocol_sha256", "protocol")):
        auth[field] = hash_bytes(artifacts[role])
    kwargs["authorization"] = artifacts["authorization"] = enc(auth)
    kwargs["trust_roots"] = roots(kwargs)
    result = module.build_stream_stock_pipeline(**kwargs)
    return dict(pipeline_result=result, candidate_source=old["candidate_source"], evidence_artifacts=artifacts,
                trust_roots=package.StreamStudyTrustRoots("fixture", tuple((role, hash_bytes(artifacts[role])) for role in package.STREAM_ROLES)))


def test_stream_pipeline_to_disabled_qc_package_and_order_path_is_end_to_end():
    obj = package.build_backtest_study_package(**make_stream_package_fixture())
    body = obj.to_payload()
    assert body["signal_count"] == 1 and body["candidate_enabled"] is False
    assert len(body["artifact_sha256s"]) == 12
    assert _analyze(obj, _terminal(obj))["order_path_verified"] is True
    assert _analyze(obj, _terminal(obj))["ib5_pass"] is False


@pytest.mark.parametrize("role", package.STREAM_ROLES)
def test_stream_package_must_rebind_every_twelve_role_byte_image(role):
    args = make_stream_package_fixture(2)
    artifacts = {**args["evidence_artifacts"], role: args["evidence_artifacts"][role] + b" "}
    with pytest.raises(ValueError):
        package.build_backtest_study_package(**{**args, "evidence_artifacts": artifacts})


def test_transaction_preceding_source_scope_cannot_claim_complete_economic_lot():
    """Full source quarter is not complete prior same-owner/security/date lots."""
    import hashlib
    args = make_stream_pipeline_fixture(1)
    prior = args["source_evidence"].to_payload()
    stream, specs = make_stream_fixture(count=1, lookback=prior["lookback_start_session"],
                                       decision=prior["decision_session"])
    record = _record(*specs[0], raw_change=lambda raw: raw.replace(
        b"<transactionDate><value>2023-01-15</value>",
        b"<transactionDate><value>2022-12-01</value>"))
    stream = _edit_manifest(stream, lambda body: body["quarters"][0].update(
        ordered_parent_inventory_sha256=hashlib.sha256(record.entry_bytes + b"\n").hexdigest()))
    stream["parent_records"] = iter([record])
    args["source_evidence"] = build_stream_source_evidence(**stream)
    args["source_manifest"] = stream["population_manifest"]
    master = json.loads(args["security_master"])
    master["mappings"][0].update(mapping_first_session="2022-01-01", knowledge_at_utc="2022-01-01T00:00:00Z")
    args["security_master"] = enc(master)
    auth = json.loads(args["authorization"])
    auth.update(source_manifest_sha256=hash_bytes(args["source_manifest"]),
                security_master_sha256=hash_bytes(args["security_master"]))
    args["authorization"] = enc(auth)
    args["trust_roots"] = roots(args)
    with pytest.raises(ValueError, match="economic.*source|source.*economic"):
        module.build_stream_stock_pipeline(**args)


def test_equal_mutable_byte_facade_is_not_the_exact_factory_payload():
    result = module.build_stream_stock_pipeline(**make_stream_pipeline_fixture(1))
    object.__setattr__(result, "_bytes", bytearray(result._bytes))
    with pytest.raises(ValueError, match="reconstructed|altered"):
        result.to_payload()
