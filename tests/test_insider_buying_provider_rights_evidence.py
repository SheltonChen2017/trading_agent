"""Entirely invented supplied-contract fixtures; no real purchase or probe I/O."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
import hashlib
import inspect
import json

import pytest

from research import insider_buying_provider_rights_evidence as module
from research.insider_buying.backtest_study_package import qc_market_data_profile


NOW = "2026-10-06T12:00:00Z"
ACCOUNT = "acct-" + "1" * 32


def raw(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


def clause(doc, text):
    encoded = text.encode()
    start = doc.index(encoded)
    return {"document_id": "purchase", "start_byte": start, "end_byte": start + len(encoded),
            "clause_sha256": sha(encoded)}


def records(*, provider="quantconnect", historical=True, contract=True):
    doc = b"Invented account purchase. Account anchor. Local processing grant. QC storage grant. QC processing grant."
    receipt = {"kind": "insider-provider-metadata-receipt-v1", "provider": provider,
        "request_profile": module._PROFILE[provider], "http_status": 200, "body_sha256": "a" * 64,
        "body_size_bytes": 20, "body_complete": True, "disposition": module._OBSERVATIONS[provider],
        "facts": {"success": True} if provider == "quantconnect" else {},
        "http_access_observed": True, "authentication_observed": provider == "quantconnect",
        "entitlement_verified": False, "rights_verified": False, "historical_coverage_verified": False,
        "research_ready": False, "qc_backtest_authorized": False, "outcome_access_authorized": False}
    probe = {"schema": "insider-provider-metadata-one-shot-audit-v1", "provider": provider,
             "completed_at_utc": "2026-10-06T11:00:00Z", "started_sha256": "b" * 64, "receipt": receipt}
    subject = {"schema": "insider-provider-rights-subject-v1", "trust_scope": "fixture", "provider": provider,
        "account_pseudonym": ACCOUNT, "product_id": "invented-product", "dataset_id": "invented-dataset",
        "vintage_id": "invented-vintage", "vintage_kind": "historical-outcome-vintage" if historical else "current-reference-snapshot",
        "data_class": "price-and-corporate-action" if historical else "reference-metadata",
        "source_manifest_sha256": "c" * 64, "outcome_vintage_sha256": "d" * 64 if historical else None,
        "representation": "local-and-quantconnect", "platform": "QuantConnect Cloud",
        "first_session": "2022-10-03", "last_session": "2023-03-31",
        "market_data_profile": qc_market_data_profile() if historical else None,
        "clock_data_entitlements": ["SPY"] if historical else []}
    index = {"schema": "insider-provider-private-terms-index-v1", "trust_scope": "fixture",
        "subject_sha256": sha(raw(subject)), "probe_receipt_sha256": sha(raw(probe)),
        "effective_at_utc": "2026-10-01T00:00:00Z", "expires_at_utc": "2026-11-01T00:00:00Z",
        "documents": [{"document_id": "purchase", "sha256": sha(doc), "byte_length": len(doc),
                       "kind": "account-purchase", "account_pseudonym": ACCOUNT, "product_id": "invented-product"}]}
    assessment = {"schema": "insider-provider-contract-permission-assessment-v1", "trust_scope": "fixture",
        "subject_sha256": sha(raw(subject)), "probe_receipt_sha256": sha(raw(probe)), "terms_index_sha256": sha(raw(index)),
        "assessed_at_utc": "2026-10-05T00:00:00Z", "assessment_basis": "externally-reviewed-applicable-contract",
        "account_identity_binding": clause(doc, "Account anchor."), "permissions": [
            {"permission": name, "status": "GRANTED", "basis": "applicable-contract-grant",
             "clause_bindings": [clause(doc, text)]} for name, text in zip(module.PERMISSIONS,
                ("Local processing grant.", "QC storage grant.", "QC processing grant."), strict=True)]}
    return {"probe": probe, "subject": subject, "index": index if contract else None,
            "assessment": assessment if contract else None, "docs": (doc,) if contract else ()}


def inputs(state):
    probe, subject = raw(state["probe"]), raw(state["subject"])
    index = None if state["index"] is None else deepcopy(state["index"])
    assessment = None if state["assessment"] is None else deepcopy(state["assessment"])
    if index is not None:
        index.update(subject_sha256=sha(subject), probe_receipt_sha256=sha(probe))
        assessment.update(subject_sha256=sha(subject), probe_receipt_sha256=sha(probe), terms_index_sha256=sha(raw(index)))
    index_raw, assessment_raw = (None if index is None else raw(index)), (None if assessment is None else raw(assessment))
    roots = module.ProviderRightsTrustRoots(state["subject"]["trust_scope"], sha(probe), sha(subject),
                None if index is None else sha(index_raw), None if assessment is None else sha(assessment_raw))
    return {"probe_receipt_raw": probe, "subject_raw": subject, "trust_roots": roots, "evaluated_at_utc": NOW,
            "terms_index_raw": index_raw, "permission_assessment_raw": assessment_raw, "term_document_bytes": state["docs"]}


def admit(state):
    return module.admit_provider_rights_evidence(**inputs(state))


def project(result, state):
    return result.backtest_rights_declaration(expected_subject_sha256=sha(raw(state["subject"])),
        expected_account_pseudonym=state["subject"]["account_pseudonym"],
        expected_source_manifest_sha256=state["subject"]["source_manifest_sha256"],
        expected_outcome_vintage_sha256=state["subject"]["outcome_vintage_sha256"], evaluated_at_utc=NOW)


@pytest.mark.parametrize("provider", module.PROVIDERS)
def test_probe_only_never_becomes_permission_product_coverage_or_authority(provider):
    result = admit(records(provider=provider, historical=False, contract=False)).to_payload()
    assert result["permission_status"] == dict.fromkeys(module.PERMISSIONS, "UNMEASURED")
    assert result["contract"] is None
    observation = result["probe_observation"]
    assert observation["authentication_observed"] is (provider == "quantconnect")
    assert observation["public_metadata_observed"] is (provider != "quantconnect")
    assert observation["purchased_product_entitlement"] == observation["historical_coverage"] == "UNMEASURED"
    assert observation["account_identity_verified_here"] is False
    for flag in ("document_authenticity_verified_here", "legal_interpretation_performed_here", "research_ready",
                 "qc_entitlement_verified_here", "permanent_look_allocated", "source_pit_rights_look_qc_backtest_execution_authority"):
        assert result[flag] is False


def test_exact_private_assessment_projection_cross_hashes_not_entitlement_or_authority():
    state = records()
    result = admit(state)
    payload = result.to_payload()
    assert payload["permission_status"] == dict.fromkeys(module.PERMISSIONS, "GRANTED")
    assert payload["contract"]["current_at_evaluation"] is True
    mapped = project(result, state)
    assert mapped["rights_artifact"]["permissions"] == list(module.PERMISSIONS)
    assert mapped["rights_artifact"]["market_data_profile"] == qc_market_data_profile()
    assert mapped["rights_artifact_sha256"] == sha(raw(mapped["rights_artifact"]))
    assert mapped["evidence_sha256"] == result.sha256
    assert mapped["source_manifest_sha256"] == state["subject"]["source_manifest_sha256"]
    for name in ("subject", "probe_receipt", "terms_index", "permission_assessment"):
        assert mapped[name + "_sha256"] == payload["roots"][name + "_sha256"]
    assert mapped["qc_entitlement_verified_here"] is False
    assert mapped["source_pit_rights_look_qc_backtest_execution_authority"] is False
    assert "registered_look_id" not in mapped
    assert "qc_entitlement" not in mapped


def test_private_bytes_are_not_retained_and_result_is_detached_sealed():
    state = records()
    result = admit(state)
    assert b"Account anchor." not in result._bytes
    assert b"Local processing grant." not in result._bytes
    state["subject"]["dataset_id"] = "changed"
    first = result.to_payload()
    first["subject"]["dataset_id"] = "mutated"
    assert result.to_payload()["subject"]["dataset_id"] == "invented-dataset"
    with pytest.raises(FrozenInstanceError):
        result._bytes = b"{}"
    with pytest.raises(module.ProviderRightsEvidenceError, match="factory-result"):
        module.ProviderRightsEvidence(result._bytes).to_payload()
    object.__setattr__(result, "_bytes", b"{}")
    with pytest.raises(module.ProviderRightsEvidenceError, match="factory-result"):
        result.to_payload()


@pytest.mark.parametrize("permission", module.PERMISSIONS)
@pytest.mark.parametrize("status", ("REFUSED", "UNMEASURED"))
def test_individual_refusal_and_missing_permission_remain_distinct_and_prevent_projection(permission, status):
    state = records()
    row = state["assessment"]["permissions"][module.PERMISSIONS.index(permission)]
    row["status"] = status
    row["basis"] = "applicable-contract-refusal" if status == "REFUSED" else "not-established"
    if status == "UNMEASURED":
        row["clause_bindings"] = []
    result = admit(state)
    assert result.to_payload()["permission_status"][permission] == status
    with pytest.raises(module.ProviderRightsEvidenceError, match="not-granted"):
        project(result, state)


def test_http_authentication_refusal_is_not_contract_refusal():
    state = records()
    state["probe"]["receipt"].update(http_status=403, disposition="authentication-http-refused", facts={}, authentication_observed=False)
    result = admit(state).to_payload()
    assert result["probe_observation"]["authentication_observed"] is False
    assert result["permission_status"] == dict.fromkeys(module.PERMISSIONS, "GRANTED")
    assert result["qc_entitlement_verified_here"] is False


def test_expired_grant_recorded_but_never_projected_as_current():
    state = records()
    state["index"]["expires_at_utc"] = "2026-10-06T12:00:00Z"
    result = admit(state)
    assert result.to_payload()["contract"]["current_at_evaluation"] is False
    assert result.to_payload()["permission_status"]["local-process"] == "GRANTED"
    with pytest.raises(module.ProviderRightsEvidenceError, match="not-current"):
        project(result, state)


def test_all_explicit_unmeasured_contract_rows_do_not_create_private_account_proof():
    state = records()
    state["assessment"].update(assessment_basis="not-established", account_identity_binding=None)
    for row in state["assessment"]["permissions"]:
        row.update(status="UNMEASURED", basis="not-established", clause_bindings=[])
    assert admit(state).to_payload()["contract"]["private_account_contract_binding_supplied"] is False


def test_public_terms_may_be_explicitly_incorporated_but_need_private_applicability_anchor():
    state = records()
    public = b"Invented incorporated applicable grant clause."
    descriptor = {"document_id": "public", "sha256": sha(public), "byte_length": len(public),
                  "kind": "public-incorporated-terms", "account_pseudonym": None, "product_id": "invented-product"}
    state["docs"] += (public,)
    state["index"]["documents"].append(descriptor)
    binding = {"document_id": "public", "start_byte": 0, "end_byte": len(public), "clause_sha256": sha(public)}
    for row in state["assessment"]["permissions"]:
        row["clause_bindings"] = [binding]
    assert project(admit(state), state)["rights_artifact"]["permissions"] == list(module.PERMISSIONS)
    state["assessment"]["account_identity_binding"] = binding
    with pytest.raises(module.ProviderRightsEvidenceError, match="public-terms-do-not-bind"):
        admit(state)


def test_provider_confirmation_requires_an_actual_private_confirmation_clause():
    state = records()
    state["assessment"]["assessment_basis"] = "provider-account-confirmation"
    for row in state["assessment"]["permissions"]:
        row["basis"] = "provider-account-confirmed-grant"
    with pytest.raises(module.ProviderRightsEvidenceError, match="confirmation-clause-missing"):
        admit(state)
    state["index"]["documents"][0]["kind"] = "provider-account-confirmation"
    assert admit(state).to_payload()["permission_status"]["qc-process"] == "GRANTED"


@pytest.mark.parametrize("basis", ("agent-delegation", "owner-preauthorization", "key-present", "authenticated",
                                    "public-terms", "public-catalog-available"))
def test_noncontract_basis_cannot_infer_grant(basis):
    state = records()
    state["assessment"]["assessment_basis"] = basis
    with pytest.raises(module.ProviderRightsEvidenceError, match="not-permission"):
        admit(state)


@pytest.mark.parametrize("path,value", [
    (("index", "documents", 0, "account_pseudonym"), "acct-" + "2" * 32),
    (("index", "documents", 0, "product_id"), "other-product"),
    (("index", "documents", 0, "byte_length"), 0),
    (("index", "documents", 0, "sha256"), "e" * 64),
    (("index", "documents", 0, "kind"), "public-availability"),
    (("assessment", "permissions", 0, "permission"), "qc-store"),
    (("assessment", "permissions", 0, "status"), True),
    (("assessment", "permissions", 0, "basis"), "authenticated-grant"),
    (("assessment", "permissions", 0, "clause_bindings"), []),
    (("assessment", "permissions", 0, "clause_bindings", 0, "clause_sha256"), "f" * 64),
    (("assessment", "permissions", 0, "clause_bindings", 0, "start_byte"), -1),
    (("assessment", "account_identity_binding"), None),
    (("assessment", "assessed_at_utc"), "2026-10-07T00:00:00Z"),
    (("assessment", "assessed_at_utc"), "2026-09-01T00:00:00Z"),
    (("index", "expires_at_utc"), "2026-09-01T00:00:00Z"),
])
def test_reanchored_bad_contract_is_still_refused(path, value):
    state = records()
    target = state
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(module.ProviderRightsEvidenceError):
        admit(state)


@pytest.mark.parametrize("flag", ("entitlement_verified", "rights_verified", "historical_coverage_verified",
                                  "research_ready", "qc_backtest_authorized", "outcome_access_authorized"))
def test_metadata_receipt_cannot_promote_permissions_or_authority(flag):
    state = records(contract=False)
    state["probe"]["receipt"][flag] = True
    with pytest.raises(module.ProviderRightsEvidenceError, match="cannot-promote"):
        admit(state)


@pytest.mark.parametrize("path,value", [
    (("probe", "provider"), "massive"), (("probe", "completed_at_utc"), "2026-10-07T00:00:00Z"),
    (("probe", "receipt", "authentication_observed"), False),
    (("probe", "receipt", "facts"), {"success": 1}),
    (("probe", "receipt", "http_status"), True),
    (("probe", "receipt", "body_complete"), False),
    (("probe", "receipt", "body_size_bytes"), 0),
    (("probe", "receipt", "disposition"), "product-entitlement-observed"),
    (("subject", "account_pseudonym"), "actual-account-id"),
    (("subject", "first_session"), "2024-01-01"),
    (("subject", "outcome_vintage_sha256"), None),
    (("subject", "source_manifest_sha256"), "bad"),
    (("subject", "data_class"), "reference-metadata"),
    (("subject", "platform"), "local"),
    (("subject", "vintage_kind"), []),
    (("subject", "clock_data_entitlements"), ["SPY", "SPY"]),
])
def test_reanchored_subject_or_probe_inconsistency_still_refused(path, value):
    state = records(contract=False)
    target = state
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(module.ProviderRightsEvidenceError):
        admit(state)


@pytest.mark.parametrize("role", ("probe_receipt_raw", "subject_raw", "terms_index_raw", "permission_assessment_raw"))
def test_changed_raw_evidence_without_independent_root_cannot_enter(role):
    values = inputs(records())
    values[role] += b" "
    with pytest.raises(module.ProviderRightsEvidenceError, match="external-root-differs"):
        module.admit_provider_rights_evidence(**values)


@pytest.mark.parametrize("role", ("terms_index_raw", "permission_assessment_raw"))
def test_partial_contract_input_is_not_an_unmeasured_fallback(role):
    values = inputs(records())
    values[role] = None
    with pytest.raises(module.ProviderRightsEvidenceError, match="partial-contract-bundle"):
        module.admit_provider_rights_evidence(**values)


@pytest.mark.parametrize("mutation", ("missing", "extra", "duplicate", "mutable", "tampered"))
def test_document_inventory_is_exact_immutable_complete_and_bound(mutation):
    state = records()
    if mutation == "missing": state["docs"] = ()
    if mutation == "extra": state["docs"] += (b"other",)
    if mutation == "duplicate":
        state["docs"] += state["docs"]
        state["index"]["documents"] += deepcopy(state["index"]["documents"])
    if mutation == "mutable": state["docs"] = list(state["docs"])
    if mutation == "tampered": state["docs"] = (state["docs"][0] + b" ",)
    with pytest.raises(module.ProviderRightsEvidenceError):
        admit(state)


@pytest.mark.parametrize("mutation", ("provider", "current-vintage", "feed", "clock", "representation"))
def test_native_package_mapping_refuses_other_provider_current_metadata_and_profile_substitutes(mutation):
    state = records(provider="sharadar" if mutation == "provider" else "quantconnect",
                    historical=mutation != "current-vintage")
    if mutation == "feed": state["subject"]["market_data_profile"]["stock_resolution"] = "daily"
    if mutation == "clock": state["subject"]["clock_data_entitlements"] = []
    if mutation == "representation":
        state["subject"].update(representation="local-only", platform="local")
    result = admit(state)
    with pytest.raises(module.ProviderRightsEvidenceError):
        project(result, state)


@pytest.mark.parametrize("field", ("expected_subject_sha256", "expected_source_manifest_sha256", "expected_outcome_vintage_sha256",
                                   "expected_account_pseudonym", "evaluated_at_utc"))
def test_projection_cannot_drift_account_source_vintage_or_assessment_clock(field):
    state = records()
    result = admit(state)
    kwargs = {"expected_subject_sha256": sha(raw(state["subject"])), "expected_account_pseudonym": ACCOUNT,
              "expected_source_manifest_sha256": "c" * 64, "expected_outcome_vintage_sha256": "d" * 64,
              "evaluated_at_utc": NOW}
    kwargs[field] = "acct-" + "2" * 32 if field == "expected_account_pseudonym" else (
        "2026-10-06T13:00:00Z" if field == "evaluated_at_utc" else "e" * 64)
    with pytest.raises(module.ProviderRightsEvidenceError):
        result.backtest_rights_declaration(**kwargs)


@pytest.mark.parametrize("invalid", (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}', b'{"x":1.0}', b'\xff', b'[]'))
def test_duplicate_nonfinite_noninteger_nonutf8_or_nonobject_json_is_refused(invalid):
    values = inputs(records(contract=False))
    values["subject_raw"] = invalid
    roots = values["trust_roots"]
    values["trust_roots"] = module.ProviderRightsTrustRoots("fixture", roots.probe_receipt_sha256, sha(invalid))
    with pytest.raises(module.ProviderRightsEvidenceError):
        module.admit_provider_rights_evidence(**values)


def test_real_scope_label_is_not_authentication_or_permission():
    state = records(contract=False)
    state["subject"]["trust_scope"] = "production"
    report = admit(state).to_payload()
    assert report["trust_scope"] == "production"
    assert report["external_roots_are_not_authentication"] is True
    assert report["permission_status"] == dict.fromkeys(module.PERMISSIONS, "UNMEASURED")
    assert report["research_ready"] is False


@pytest.mark.parametrize("mutation", ("unknown-field", "nested-value", "bool-coercion", "missing-field"))
def test_profile_has_a_narrow_exact_known_field_and_scalar_shape(mutation):
    state = records(contract=False)
    profile = state["subject"]["market_data_profile"]
    if mutation == "unknown-field": profile["arbitrary"] = {"nested": "not a profile field"}
    if mutation == "nested-value": profile["provider"] = {"nested": "not a scalar provider identity"}
    if mutation == "bool-coercion": profile["stock_fill_forward"] = 0
    if mutation == "missing-field": del profile["clock_ticker"]
    with pytest.raises(module.ProviderRightsEvidenceError):
        admit(state)


def test_pure_module_has_no_loader_transport_credential_look_or_job_imports():
    source = inspect.getsource(module)
    for forbidden in ("import os", "import pathlib", "import socket", "import subprocess", "import urllib",
                      "from research.quantconnect", "open(", "read_bytes(", "os.environ"):
        assert forbidden not in source
    assert "https://www.quantconnect.com/terms" in source
    assert "https://sharadar.com/terms" in source
