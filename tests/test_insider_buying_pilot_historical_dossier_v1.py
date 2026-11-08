"""Invented filings only; caller supplies native network/DATA isolation."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from research import insider_buying_pilot_historical_dossier_v1 as m


def _helper(name):
    path = Path(__file__).with_name(name)
    spec = importlib.util.spec_from_file_location("dossier_fixture_" + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sec = _helper("test_insider_buying_sec_complete_submission.py")
ref = _helper("test_insider_buying_pilot_pit_retained_audit_v1.py")


def _xml(contents="", *, owners=("0000999999",)):
    source = sec._xml(owners)
    source = source.replace(b"</issuer>", b"<issuerTradingSymbol>INVENTED</issuerTradingSymbol></issuer>")
    return source.replace(b"</ownershipDocument>", contents.encode() + b"</ownershipDocument>")


def _project(contents="", *, owners=("0000999999",)):
    return sec._project(sec._complete(xml=_xml(contents, owners=owners), owners=owners))


def _entry(kind="nonDerivativeTransaction", title="Invented Class A"):
    return (f"<{kind}><securityTitle><value>{title}</value></securityTitle>"
        "<transactionAmounts><transactionPricePerShare><value>987654321.875</value>"
        f"</transactionPricePerShare></transactionAmounts></{kind}>")


def _evidence(contents=None):
    if contents is None:
        contents = "<nonDerivativeTable>" + _entry() + "</nonDerivativeTable>"
    return m.extract_identity(_project(contents))


def _identity():
    sources = {"research/invented_dossier.py": "a" * 64}
    return {"head": "b" * 40, "sources": sources, "source_inventory_sha256":
            hashlib.sha256(m._raw(sources)).hexdigest()}


def _inputs():
    evidence = _evidence()
    case = {"case_id": "INVENTED-CONTROL", "cik": evidence["issuer_cik"],
            "accession": evidence["accession"], "form_type": evidence["form_type"],
            "filing_date": evidence["filing_date"], "acceptance_digits": evidence["acceptance_digits"],
            "source_symbol": evidence["source_symbol"], "body_sha256": evidence["body_sha256"]}
    cases = [case]
    audited = m.audit.build_audit(*ref._inputs(cases=cases))
    return cases, [evidence], audited, "c" * 64, _identity()


def _build():
    return m.build_dossier(*_inputs())


def test_extracts_only_original_identity_and_exact_title_metadata():
    projected = _project("<nonDerivativeTable>" + _entry() + "</nonDerivativeTable>",
                         owners=("0000999999", "0000888888"))
    value = m.extract_identity(projected)
    assert value["body_sha256"] == hashlib.sha256(projected.raw_bytes).hexdigest()
    assert value["body_bytes"] == len(projected.raw_bytes)
    assert value["reporting_owner_ciks"] == ["0000999999", "0000888888"]
    assert value["header_xml_owner_sets_agree"] is True
    assert value["security_titles"] == [{"kind": "nonDerivativeTransaction", "source_ordinal": 1,
        "title_raw": "Invented Class A", "disposition": "metadata_observed"}]
    assert value["acceptance_digits"] == "20221107101112"
    assert value["source_symbol"] == "INVENTED"
    assert value["financial_values_interpreted"] is value["acceptance_is_public_delivery"] is False
    assert value["historical_validity_interval"] is value["historical_public_known_by"] is None
    wire = m._raw(value)
    assert b"987654321.875" not in wire and b"Invented Owner" not in wire


@pytest.mark.parametrize("kind", ("nonDerivativeTransaction", "nonDerivativeHolding",
                                  "derivativeTransaction", "derivativeHolding"))
def test_all_four_entry_kinds_preserve_exact_title_and_lineage(kind):
    table = "nonDerivativeTable" if kind.startswith("nonDerivative") else "derivativeTable"
    value = _evidence(f"<{table}>" + _entry(kind, " Exact Class B ") + f"</{table}>")
    assert value["security_titles"][0]["kind"] == kind
    assert value["security_titles"][0]["title_raw"] == " Exact Class B "
    assert value["known_entry_count"] == 1 and value["entries_missing_security_title"] == 0


@pytest.mark.parametrize("inside,code", (
    ("<value></value>", "title_text_refused"),
    ("<value>line1&#10;line2</value>", "title_text_refused"),
    ("<value><nested>PRIVATE TITLE</nested></value>", "title_shape_refused"),
    ("<value>PRIVATE TITLE</value><value>OTHER</value>", "title_shape_refused"),
))
def test_malformed_title_stays_counted_as_quarantined_without_copying_source(inside, code):
    body = f"<nonDerivativeTable><nonDerivativeTransaction><securityTitle>{inside}</securityTitle>"
    body += "</nonDerivativeTransaction></nonDerivativeTable>"
    value = _evidence(body)
    assert len(value["security_titles"]) == 1
    assert value["security_titles"][0]["disposition"] == code
    assert value["security_titles"][0]["title_raw"] is None
    assert b"PRIVATE TITLE" not in m._raw(value)


def test_missing_duplicate_and_unplaced_titles_are_not_silently_dropped():
    body = ("<nonDerivativeTable><nonDerivativeTransaction></nonDerivativeTransaction>"
        "<nonDerivativeHolding><securityTitle><value>A</value></securityTitle>"
        "<securityTitle><value>B</value></securityTitle></nonDerivativeHolding></nonDerivativeTable>"
        "<unrelated><securityTitle><value>UNPLACED</value></securityTitle></unrelated>")
    value = _evidence(body)
    assert value["known_entry_count"] == 2 and value["entries_missing_security_title"] == 1
    assert value["unplaced_security_title_count"] == 1
    assert len(value["security_titles"]) == 2
    assert all(v["disposition"] == "title_shape_refused" for v in value["security_titles"])
    assert b"UNPLACED" not in m._raw(value)


def test_tampered_frozen_projection_and_foreign_objects_are_refused():
    with pytest.raises(m.HistoricalDossierError, match="original_projection_required"):
        m.extract_identity({})
    projected = _project()
    object.__setattr__(projected, "accepted_at_raw", "20221107101113")
    with pytest.raises(m.HistoricalDossierError, match="original_identity_refused"):
        m.extract_identity(projected)


def test_dossier_keeps_current_context_separate_and_all_historical_gates_false():
    result = _build()
    private = m.private_payload(result)
    assert private["counts"]["controls"] == private["counts"]["originals_reparsed"] == 1
    assert private["counts"]["distinct_reporting_owners"] == 1
    assert private["counts"]["observed_security_titles"] == 1
    assert private["counts"]["historical_identity_gate_closures"] == 0
    control = private["controls"][0]
    assert control["historical_validity_interval"] is control["historical_public_known_by"] is None
    assert control["historical_share_class_binding_verified"] is False
    assert control["current_reference_evidence"]["counts"]["current_candidate_permatickers"] == 1
    assert control["original_identity"]["reporting_owner_ciks"] == ["0000999999"]
    assert private["authority"] == control["authority"] == m.audit.authority()
    assert private["historical_physical_continuity_established"] is private["historical_binding_passed"] is False
    assert private["all_six_form_coverage_verified"] is False
    public = m.public_summary(result)
    assert public["dossier_sha256"] == hashlib.sha256(m._raw(private)).hexdigest()
    wire = m._raw(public)
    assert all(s not in wire for s in (b"0000999999", b"0000123456", b"INVENTED", b"Class A", b"987654321.875"))


@pytest.mark.parametrize("fault", ("cloned-evidence", "mutated-evidence", "body-pin", "case-pin", "reference-clone", "reference-mutated"))
def test_forged_cloned_changed_or_misaligned_evidence_is_refused(fault):
    values = list(_inputs())
    if fault == "cloned-evidence": values[1] = deepcopy(values[1])
    elif fault == "mutated-evidence": values[1][0]["reporting_owner_ciks"] = ["0000111111"]
    elif fault == "body-pin": values[0][0]["body_sha256"] = "d" * 64
    elif fault == "case-pin": values[0][0]["case_id"] = "OTHER-CONTROL"
    elif fault == "reference-clone": values[2] = deepcopy(values[2])
    else: values[2]["authority"]["point_in_time_data"] = True
    with pytest.raises(m.HistoricalDossierError): m.build_dossier(*values)


@pytest.mark.parametrize("fault", ("head", "source-digest", "inventory", "escape", "extra"))
def test_execution_identity_is_strict_and_hash_bound(fault):
    values = list(_inputs()); identity = values[4]
    if fault == "head": identity["head"] = "b" * 39
    elif fault == "source-digest": identity["sources"]["research/invented_dossier.py"] = "invalid"
    elif fault == "inventory": identity["source_inventory_sha256"] = "d" * 64
    elif fault == "escape":
        identity["sources"] = {"../private.py": "a" * 64}
        identity["source_inventory_sha256"] = hashlib.sha256(m._raw(identity["sources"])).hexdigest()
    else: identity["unverified"] = True
    with pytest.raises(m.HistoricalDossierError, match="dossier_execution_refused"):
        m.build_dossier(*values)


@pytest.mark.parametrize("fault", ("fixture-int", "false-actual", "bad-transition", "extra-case", "missing-evidence"))
def test_scope_shape_and_fixture_controls_cannot_release_an_actual_dossier(fault):
    values = list(_inputs()); kwargs = {}
    if fault == "fixture-int": kwargs["fixture_only"] = 1
    elif fault == "false-actual": kwargs["fixture_only"] = False
    elif fault == "bad-transition": values[3] = "not-a-transition-pin"
    elif fault == "extra-case": values[0][0]["historical_identity_verified"] = True
    else: values[1] = []
    with pytest.raises(m.HistoricalDossierError): m.build_dossier(*values, **kwargs)


def test_private_payload_is_a_copy_and_public_summary_refuses_forged_or_mutated_dossier():
    result = _build(); value = m.private_payload(result)
    value["controls"][0]["original_identity"]["reporting_owner_ciks"].clear()
    assert m.private_payload(result)["controls"][0]["original_identity"]["reporting_owner_ciks"]
    with pytest.raises(m.HistoricalDossierError, match="genuine_dossier_evidence_required"):
        m.public_summary(deepcopy(result))
    result["authority"]["backtesting_ready"] = True
    with pytest.raises(m.HistoricalDossierError, match="genuine_dossier_evidence_required"):
        m.public_summary(result)


def test_dossier_title_and_unplaced_accounting_preserves_every_observation():
    values = list(_inputs())
    evidence = _evidence("<nonDerivativeTable>" + _entry(title="") + "</nonDerivativeTable>"
        "<outside><securityTitle><value>UNPLACED</value></securityTitle></outside>")
    case = values[0][0]
    case["body_sha256"] = evidence["body_sha256"]
    values[1] = [evidence]
    values[2] = m.audit.build_audit(*ref._inputs(cases=values[0]))
    result = m.build_dossier(*values)
    counts = m.public_summary(result)["counts"]
    assert counts["security_title_occurrences"] == counts["quarantined_security_titles"] == 1
    assert counts["unplaced_security_titles"] == 1 and counts["observed_security_titles"] == 0


def test_serialized_readback_reconstructs_counts_reference_digest_and_safe_summary():
    result = _build(); payload = json.loads(m._raw(m.private_payload(result)))
    checked = m.validate_payload(payload, "c" * 64, _identity(), fixture_only=True)
    assert checked == payload and checked is not payload
    assert m.summary_from_payload(payload, "c" * 64, _identity(), fixture_only=True) == m.public_summary(result)
    checked["controls"].clear()
    assert payload["controls"]


@pytest.mark.parametrize("fault", ("extra-top", "schema", "fixture-alias", "transition", "execution", "reference-pin",
    "extra-control", "case-hash", "original-extra", "body-size", "owner-invalid", "owner-duplicate", "owner-agreement",
    "symbol", "header-parent", "xml-extra", "xml-name", "xml-size", "title-extra", "title-ordinal", "title-kind",
    "title-disposition", "title-text", "title-count", "missing-count", "body-financial", "body-availability",
    "body-knownby", "control-knownby", "class-verified", "authority", "control-authority", "top-positive",
    "reference-extra", "reference-authority", "reference-knownby", "reference-count", "reference-guarantee",
    "reference-digest", "summary-count", "summary-bool", "category-conservation", "request-conservation",
    "extra-summary", "source-pin", "source-extra"))
def test_serialized_readback_refuses_unknown_fields_false_authority_and_broken_bindings(fault):
    payload = m.private_payload(_build())
    control = payload["controls"][0]; original = control["original_identity"]
    context = control["current_reference_evidence"]
    if fault == "extra-top": payload["other"] = True
    elif fault == "schema": payload["schema"] = "foreign"
    elif fault == "fixture-alias": payload["fixture_only"] = 1
    elif fault == "transition": payload["transition_sha256"] = "d" * 64
    elif fault == "execution": payload["execution_identity"]["head"] = "d" * 40
    elif fault == "reference-pin": payload["reference_audit_sha256"] = "d" * 64
    elif fault == "extra-control": control["other"] = True
    elif fault == "case-hash": control["control_sha256"] = "d" * 64
    elif fault == "original-extra": original["historical_identity_verified"] = True
    elif fault == "body-size": original["body_bytes"] = True
    elif fault == "owner-invalid": original["reporting_owner_ciks"] = ["not-a-cik"]
    elif fault == "owner-duplicate": original["reporting_owner_ciks"] *= 2
    elif fault == "owner-agreement": original["header_xml_owner_sets_agree"] = 1
    elif fault == "symbol": original["source_symbol"] = ["PRIVATE"]
    elif fault == "header-parent": original["header_pin"]["parent_sha256"] = "d" * 64
    elif fault == "xml-extra": original["xml_pin"]["other"] = True
    elif fault == "xml-name": original["xml_pin"]["filename"] = "../outside.xml"
    elif fault == "xml-size": original["xml_pin"]["size_bytes"] = original["body_bytes"]
    elif fault == "title-extra": original["security_titles"][0]["other"] = True
    elif fault == "title-ordinal": original["security_titles"][0]["source_ordinal"] = True
    elif fault == "title-kind": original["security_titles"][0]["kind"] = "unrelated"
    elif fault == "title-disposition": original["security_titles"][0]["disposition"] = "assumed"
    elif fault == "title-text": original["security_titles"][0]["title_raw"] = "PRIVATE\nTEXT"
    elif fault == "title-count": original["known_entry_count"] = 0
    elif fault == "missing-count": original["entries_missing_security_title"] = 2
    elif fault == "body-financial": original["financial_values_interpreted"] = True
    elif fault == "body-availability": original["acceptance_is_public_delivery"] = True
    elif fault == "body-knownby": original["historical_public_known_by"] = "2022-11-07T09:00:00Z"
    elif fault == "control-knownby": control["historical_public_known_by"] = "2022-11-07T09:00:00Z"
    elif fault == "class-verified": control["historical_share_class_binding_verified"] = True
    elif fault == "authority": payload["authority"]["point_in_time_data"] = True
    elif fault == "control-authority": control["authority"]["rights_verified"] = True
    elif fault == "top-positive": payload["historical_physical_continuity_established"] = True
    elif fault == "reference-extra": context["other"] = True
    elif fault == "reference-authority": context["authority"]["historical_identity_verified"] = True
    elif fault == "reference-knownby": context["public_known_by"] = "2022-11-07"
    elif fault == "reference-count": context["counts"]["fmp_joint_rows"] = 100
    elif fault == "reference-guarantee": context["fmp_form_exact_row_guaranteed"] = False
    elif fault == "reference-digest": context["candidate_permatickers_sha256"] = "d" * 64
    elif fault == "summary-count": payload["counts"]["originals_reparsed"] = 2
    elif fault == "summary-bool": payload["counts"]["historical_identity_gate_closures"] = False
    elif fault == "category-conservation": payload["reference_counts"]["action_categories"]["other"] += 1
    elif fault == "request-conservation": payload["reference_counts"]["provider_unattempted_requests"] += 1
    elif fault == "extra-summary": payload["reference_counts"]["other"] = 1
    elif fault == "source-pin": payload["reference_source_pins"][next(iter(payload["reference_source_pins"]))]["bytes"] = True
    else: payload["reference_source_pins"][next(iter(payload["reference_source_pins"]))]["other"] = 1
    with pytest.raises(m.HistoricalDossierError):
        m.validate_payload(payload, "c" * 64, _identity(), fixture_only=True)


def test_serialized_readback_expected_binding_arguments_are_not_taken_from_payload():
    payload = m.private_payload(_build())
    for transition, identity, fixture in (("d" * 64, _identity(), True),
            ("c" * 64, {**_identity(), "head": "d" * 40}, True), ("c" * 64, _identity(), False)):
        with pytest.raises(m.HistoricalDossierError):
            m.validate_payload(payload, transition, identity, fixture_only=fixture)
