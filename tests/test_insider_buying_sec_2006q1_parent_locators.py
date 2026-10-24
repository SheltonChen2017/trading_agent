"""Invented full source metadata only; process-tree network denial is external."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json

import pytest

import research.insider_buying_sec_2006q1_parent_locators as locators
from test_insider_buying_earnings_issuer_inventory import _assess, _row


def _bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _master(*rows):
    return (b"Description: Master Index of EDGAR Dissemination Feed\n"
            b"Last Data Received: March 31, 2006\n"
            b"Comments: webmaster@sec.gov\n\n"
            b"CIK|Company Name|Form Type|Date Filed|Filename\n"
            b"--------------------------------------------------------------------------------\n" + b"".join(rows))


def _path(ordinal=1, *, folder="123", form="4", filed="2006-01-03", accession=None):
    accession = f"0000000123-06-{ordinal:06d}" if accession is None else accession
    return f"999|Invented index filer|{form}|{filed}|edgar/data/{folder}/{accession}.txt\n".encode()


def _exposure(records=None):
    return _bytes({"schema": locators.EXPOSURE_SCHEMA, "records": [] if records is None else records})


def _exposed(ordinal=1, state="completed", accession=None):
    accession = f"0000000123-06-{ordinal:06d}" if accession is None else accession
    return {"accession_number": accession, "accession_key_sha256": locators.accession_key(accession),
            "evidence": [{"root_id": "invented-root-v1", "journal_sha256": "a" * 64, "state": state}]}


def _build(rows=None, master=None, exposures=None, *, inventory_raw=None, **kwargs):
    inventory_raw = _assess(rows).canonical_bytes() if inventory_raw is None else inventory_raw
    master = _master(_path()) if master is None else master
    exposures = _exposure() if exposures is None else exposures
    return locators.build_2006q1_parent_locators(inventory_raw, master, exposures,
        expected_inventory_sha256=_sha(inventory_raw), expected_master_sha256=_sha(master),
        expected_prior_exposure_sha256=_sha(exposures), **kwargs)


def test_complete_six_form_source_ordinals_context_and_all_false_authority():
    rows = [_row(i, DOCUMENT_TYPE=form) for i, form in enumerate(locators.FORMS, 1)]
    report = _build(rows, _master(_path(3), _path(4, form="4/A"))).to_payload()
    assert report["source_filings"] == 6
    assert report["form_counts"] == {form: 1 for form in locators.FORMS}
    assert [r["source_record_ordinal"] for r in report["filing_accounting"]] == list(range(1, 7))
    assert report["counts"]["target_filings"] == 2
    assert report["counts"]["context_filings"] == 4
    assert report["fresh_locator_count"] == 2
    assert report["all_source_filings_accounted_relative_to_supplied_bytes"] is True
    assert report["retained_source_hashes_match"] is False
    assert len(report["authority"]) == 14 and all(v is False for v in report["authority"].values())
    assert report["provider_dispatches"] == report["research_looks"] == report["qc_jobs"] == 0
    assert b"INVENTED PRIVATE" not in _bytes(report)
    assert "period_of_report" not in report


def test_as_indexed_reporter_folder_retained_without_issuer_cik_guess():
    report = _build(master=_master(_path(folder="987654"))).to_payload()
    request = report["prefix"][0]
    assert request["url"] == "https://www.sec.gov/Archives/edgar/data/987654/0000000123-06-000001.txt"
    assert request["issuer_cik"] == "0000000123"
    assert report["counts"]["selected_archive_folder_differs_from_issuer"] == 1
    assert request["accession_key_sha256"] == _sha(b"0000000123-06-000001")
    assert all(len(request[k]) == 64 for k in ("filing_metadata_sha256", "submission_inventory_sha256",
        "quarterly_zip_sha256", "submission_member_sha256", "master_decoded_sha256", "master_receipt_sha256"))


def test_multiple_aliases_select_only_unique_numeric_issuer_folder_and_preserve_all():
    report = _build(master=_master(_path(folder="0123"), _path(folder="234"))).to_payload()
    assert len(report["filing_accounting"][0]["master_aliases"]) == 2
    assert report["prefix"][0]["archive_path"].startswith("edgar/data/0123/")
    assert report["counts"]["multi_alias_unique_issuer_path_resolved"] == 1


@pytest.mark.parametrize("folders", [("234", "345"), ("123", "0123")])
def test_ambiguous_aliases_quarantined_not_tie_broken(folders):
    report = _build(master=_master(*[_path(folder=folder) for folder in folders])).to_payload()
    assert report["prefix"] == []
    assert report["filing_accounting"][0]["selected_locator"] is None
    assert report["counts"]["multiple_master_aliases_without_unique_issuer_path"] == 1


def test_form_and_date_disagreements_both_counted_without_partial_admission():
    report = _build(master=_master(_path(form="4/A", filed="2006-01-04"))).to_payload()
    assert report["prefix"] == []
    assert report["filing_accounting"][0]["quarantine_reasons"] == [
        "master_form_disagreement", "master_filing_date_disagreement"]
    assert report["counts"]["master_form_disagreement"] == report["counts"]["master_filing_date_disagreement"] == 1


def test_any_alias_disagreement_refuses_even_when_unique_issuer_path_matches():
    report = _build(master=_master(_path(), _path(folder="234", filed="2006-01-04"))).to_payload()
    assert report["prefix"] == []
    assert report["counts"]["master_filing_date_disagreement"] == 1


def test_missing_master_and_extra_accessions_preserve_denominator():
    report = _build([_row(1), _row(2)], _master(_path(1), _path(9))).to_payload()
    assert report["source_filings"] == 2 and len(report["filing_accounting"]) == 2
    assert report["counts"]["master_locator_missing"] == 1
    assert report["fresh_locator_count"] == 1
    assert report["master_extra_accession_count"] == 1
    assert report["master_extra_accessions"][0]["accession_number"] == "0000000123-06-000009"


def test_context_form_with_master_target_kept_and_never_requested():
    report = _build([_row(DOCUMENT_TYPE="3")]).to_payload()
    row = report["filing_accounting"][0]
    assert report["fresh_locator_count"] == 0
    assert row["disposition"] == "context_retained_not_parent_candidate"
    assert row["quarantine_reasons"] == ["context_form_has_form4_master_locator"]
    assert report["master_extra_accession_count"] == 1


@pytest.mark.parametrize("state", sorted(locators._STATES))
def test_every_prior_exposure_state_excludes_accession_independently_of_url(state):
    report = _build(master=_master(_path(folder="987654")),
                    exposures=_exposure([_exposed(state=state)])).to_payload()
    assert report["prefix"] == [] and report["fresh_locator_count"] == 0
    row = report["filing_accounting"][0]
    assert row["prior_exposed"] is True and row["disposition"] == "locatable_prior_exposed"
    assert row["prior_exposure_evidence"][0]["state"] == state
    assert report["authority"]["prior_operational_journals_verified"] is False


def test_deterministic_chronological_prefix_does_not_change_source_order():
    rows = [_row(1, FILING_DATE="27-FEB-2006"), _row(2, FILING_DATE="06-MAR-2006"),
            _row(3, FILING_DATE="31-JAN-2006"), _row(4, FILING_DATE="31-JAN-2006")]
    master = _master(_path(4, filed="2006-01-31"), _path(2, filed="2006-03-06"),
                     _path(1, filed="2006-02-27"), _path(3, filed="2006-01-31"))
    report = _build(rows, master, _exposure([_exposed(3)]), maximum_prefix=2).to_payload()
    assert [r["source_record_ordinal"] for r in report["filing_accounting"]] == [1, 2, 3, 4]
    assert [r["source_record_ordinal"] for r in report["prefix"]] == [4, 1]
    assert report["fresh_locator_count"] == 3
    assert report["prefix_sha256"] == _sha(_bytes(report["prefix"]))
    assert report["filing_accounting_sha256"] == _sha(_bytes(report["filing_accounting"]))


def test_accession_year_mismatch_retained_not_silently_removed():
    accession = "0000000123-05-000001"
    report = _build([_row(ACCESSION_NUMBER=accession)], _master(_path(accession=accession))).to_payload()
    assert report["filing_accounting"][0]["accession_year_mismatch"] is True
    assert report["prefix"][0]["accession_number"] == accession


@pytest.mark.parametrize("name", ["inventory", "master", "exposures"])
def test_independent_external_pin_required_for_each_source(name):
    raw, master, exposed = _assess().canonical_bytes(), _master(_path()), _exposure()
    kwargs = {"expected_inventory_sha256": _sha(raw), "expected_master_sha256": _sha(master),
              "expected_prior_exposure_sha256": _sha(exposed)}
    kwargs[{"inventory": "expected_inventory_sha256", "master": "expected_master_sha256",
            "exposures": "expected_prior_exposure_sha256"}[name]] = "0" * 64
    with pytest.raises(locators.ParentLocatorError, match="external"):
        locators.build_2006q1_parent_locators(raw, master, exposed, **kwargs)


@pytest.mark.parametrize("maximum", [0, -1, True, 1.0, 4097, "64"])
def test_prefix_must_be_bounded_positive_exact_integer(maximum):
    with pytest.raises(locators.ParentLocatorError, match="prefix_bound"):
        _build(maximum_prefix=maximum)


@pytest.mark.parametrize("change", [
    lambda p: p.update(authority={}),
    lambda p: p["authority"].update(source_authenticated=True),
    lambda p: p["filings"][0].update(form_type=[]),
    lambda p: p["filings"][0].update(source_record_ordinal=True),
    lambda p: p["filings"][0].update(raw_filing_date="04-JAN-2006"),
    lambda p: p["filings"][0].update(raw_symbol_label="bad\x00label"),
    lambda p: p["filings"][0].update(issuer_cik="0000000999"),
    lambda p: p["filings"][0].update(accession_year_mismatch=True),
    lambda p: p["accounting"]["form_counts"].update({"4": True}),
    lambda p: p["accounting"].update(accession_year_mismatches=1),
    lambda p: p["accounting"].update(filings=2),
    lambda p: p.update(unregistered_extra={"text": "unknown"}),
])
def test_inconsistent_hash_bound_inventory_refused_as_whole(change):
    body = _assess().to_payload(); change(body)
    with pytest.raises(locators.ParentLocatorError):
        _build(inventory_raw=_bytes(body))


@pytest.mark.parametrize("change", [
    lambda p: p["records"][0].update(accession_key_sha256="b" * 64),
    lambda p: p["records"].append(p["records"][0]),
    lambda p: p["records"][0]["evidence"][0].update(state="planned"),
    lambda p: p["records"][0]["evidence"][0].update(root_id="../unsafe"),
    lambda p: p["records"][0]["evidence"].append(p["records"][0]["evidence"][0]),
    lambda p: p["records"][0].update(evidence=[]),
    lambda p: p.update(unexpected=True),
])
def test_prior_exposure_shape_and_key_order_are_binding(change):
    body = json.loads(_exposure([_exposed()])); change(body)
    with pytest.raises(locators.ParentLocatorError):
        _build(exposures=_bytes(body))


@pytest.mark.parametrize("source", [b"{} ", b'{"schema":"a","schema":"b"}', b'{"n":NaN}', b'\xff'])
def test_canonical_duplicate_nonfinite_or_malformed_inventory_refused(source):
    with pytest.raises(locators.ParentLocatorError):
        _build(inventory_raw=source)


def test_malformed_master_refusal_does_not_echo_source_text():
    secret = b"INVENTED-DO-NOT-LOG-ME"
    with pytest.raises(locators.ParentLocatorError) as exc:
        _build(master=secret)
    assert str(exc.value) == "master_source_schema_refused"
    assert secret.decode() not in str(exc.value)


def test_factory_weak_byte_seal_rejects_constructor_replace_and_tampering():
    genuine = _build()
    assert genuine.sha256 == _sha(genuine.canonical_bytes())
    for forged in [locators.ParentLocatorAccounting(genuine.canonical_bytes(), object()),
                   replace(genuine), replace(genuine, _raw=b"{}")]:
        with pytest.raises(locators.ParentLocatorError, match="genuine_unchanged"):
            forged.canonical_bytes()
    payload = genuine.to_payload(); payload["authority"]["backtesting_ready"] = True
    assert genuine.to_payload()["authority"]["backtesting_ready"] is False
    object.__setattr__(genuine, "_raw", b"{}")
    with pytest.raises(locators.ParentLocatorError):
        genuine.canonical_bytes()


def test_output_bound_refusal_before_return(monkeypatch):
    monkeypatch.setattr(locators, "MAX_OUTPUT_BYTES", 1)
    with pytest.raises(locators.ParentLocatorError, match="output_bound"):
        _build()


@pytest.mark.parametrize("bound", ["MAX_INVENTORY_BYTES", "MAX_EXPOSURE_BYTES"])
def test_input_bounds_refuse_before_schema_work(monkeypatch, bound):
    monkeypatch.setattr(locators, bound, 1)
    with pytest.raises(locators.ParentLocatorError, match="source_byte_bound"):
        _build()


def test_prior_exposure_outside_quarter_inventory_stays_in_input_count():
    report = _build(exposures=_exposure([_exposed(9)])).to_payload()
    assert report["prior_exposure_input_records"] == 1
    assert report["fresh_locator_count"] == 1
    assert report["counts"]["prior_exposed_targets"] == 0


def test_all_locator_dispositions_balance_full_source_denominator():
    rows = [_row(1), _row(2), _row(3), _row(4, DOCUMENT_TYPE="3")]
    report = _build(rows, _master(_path(1), _path(2), _path(4)), _exposure([_exposed(2)])).to_payload()
    counts = report["counts"]
    assert counts["context_filings"] + counts["target_filings"] == report["source_filings"]
    assert counts["locatable_unexposed"] + counts["locatable_prior_exposed"] + counts["locator_quarantined"] == counts["target_filings"]
    assert len(report["filing_accounting"]) == report["source_filings"]
    assert report["fresh_locator_count"] == counts["locatable_unexposed"]
