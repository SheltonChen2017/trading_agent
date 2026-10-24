"""Invented metadata archives only; process-tree network denial is external."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import zipfile

import pytest

if os.name != "posix":
    pytest.skip("IBWIN-CR01: private POSIX custody supported; Windows port deferred", allow_module_level=True)

import research.insider_buying_earnings_issuer_inventory as inventory


def _row(ordinal=1, **overrides):
    row = {name: "" for name in _headers()}
    row.update(ACCESSION_NUMBER=f"0000000123-06-{ordinal:06d}", FILING_DATE="03-JAN-2006",
               DOCUMENT_TYPE="4", ISSUERCIK="123", ISSUERTRADINGSYMBOL="FIXA",
               ISSUERNAME="INVENTED PRIVATE NAME NOT IN OUTPUT", REMARKS="INVENTED PRIVATE TEXT")
    row.update(overrides)
    return row


def _headers():
    return next(item.headers for item in inventory.build_retained_82q_schema_profile_candidate().variants
                if item.table_name == "SUBMISSION.tsv" and item.valid_from_year == 2006)


def _zip(rows=None, *, headers=None, extra=None, omit=None, duplicate=None, raw_submission=None):
    rows = [_row()] if rows is None else rows
    headers = _headers() if headers is None else headers
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
    writer.writerow(headers)
    for row in rows:
        writer.writerow([row.get(name, "") for name in headers])
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in inventory.ALLOWED_SEC_TABLES + inventory._AUXILIARY:
            if name == omit:
                continue
            raw = (stream.getvalue().encode() if raw_submission is None else raw_submission) if name == "SUBMISSION.tsv" else b"DO NOT INTERPRET FINANCIAL OR CUSTOMER ROWS"
            archive.writestr(name, raw)
        if extra is not None:
            archive.writestr(extra, b"extra")
        if duplicate is not None:
            with pytest.warns(UserWarning):
                archive.writestr(duplicate, b"duplicate")
    return out.getvalue()


def _assess(rows=None, **kwargs):
    raw = _zip(rows, **kwargs)
    return inventory.assess_earnings_issuer_inventory(raw, expected_archive_sha256=hashlib.sha256(raw).hexdigest())


def test_complete_all_six_forms_are_accounted_and_never_admitted():
    rows = [_row(i, DOCUMENT_TYPE=form, ISSUERCIK=str(i)) for i, form in enumerate(inventory.FORMS, start=1)]
    report = _assess(rows).to_payload()
    assert report["accounting"]["filings"] == 6
    assert report["accounting"]["form_counts"] == {form: 1 for form in inventory.FORMS}
    assert report["accounting"]["relevant_filings"] == 2
    assert report["accounting"]["context_filings"] == 4
    assert report["accounting"]["all_form_issuers"] == 6
    assert report["accounting"]["relevant_issuers"] == 2
    assert len(report["filings"]) == 6
    assert [row["source_record_ordinal"] for row in report["filings"]] == list(range(1, 7))
    assert all(value is False for value in report["authority"].values())
    assert report["research_looks"] == report["provider_dispatches"] == report["qc_jobs"] == 0
    assert report["non_submission_crc_verified"] is False
    assert report["non_submission_member_bodies_interpreted"] is False
    assert "INVENTED PRIVATE" not in json.dumps(report)
    assert "period_of_report" not in json.dumps(report).lower()


def test_legacy_filing_dates_are_chronological_not_dd_mon_lexical():
    rows = [_row(1, FILING_DATE="27-FEB-2006"), _row(2, FILING_DATE="06-MAR-2006"),
            _row(3, FILING_DATE="31-JAN-2006")]
    result = _assess(rows).to_payload()
    issuer = result["relevant_form_issuers"][0]
    assert issuer["first_filing_date"] == "2006-01-31"
    assert issuer["last_filing_date"] == "2006-03-06"
    assert [row["filing_date"] for row in result["filings"]] == ["2006-02-27", "2006-03-06", "2006-01-31"]
    assert [row["raw_filing_date"] for row in result["filings"]] == ["27-FEB-2006", "06-MAR-2006", "31-JAN-2006"]
    assert result["filing_date_dialect"] == "legacy"


def test_january31_precedes_february01_and_all_form_extrema_use_iso_dates():
    report = _assess([_row(1, FILING_DATE="31-JAN-2006"),
                      _row(2, FILING_DATE="01-FEB-2006", DOCUMENT_TYPE="3")]).to_payload()
    assert report["all_form_issuers"][0]["first_filing_date"] == "2006-01-31"
    assert report["all_form_issuers"][0]["last_filing_date"] == "2006-02-01"
    assert report["relevant_form_issuers"][0]["last_filing_date"] == "2006-01-31"


def test_aliases_collisions_empty_and_placeholders_remain_exact():
    rows = [_row(1, ISSUERCIK="20", ISSUERTRADINGSYMBOL="SINGLE"),
            _row(2, ISSUERCIK="21", ISSUERTRADINGSYMBOL="NEW"),
            _row(3, ISSUERCIK="21", ISSUERTRADINGSYMBOL="old"),
            _row(4, ISSUERCIK="22", ISSUERTRADINGSYMBOL="DUP"),
            _row(5, ISSUERCIK="23", ISSUERTRADINGSYMBOL="DUP"),
            _row(6, ISSUERCIK="24", ISSUERTRADINGSYMBOL="(NONE)"),
            _row(7, ISSUERCIK="25", ISSUERTRADINGSYMBOL="(NONE)"),
            _row(8, ISSUERCIK="26", ISSUERTRADINGSYMBOL=""),
            _row(9, ISSUERCIK="320193", ISSUERTRADINGSYMBOL="AAPL")]
    report = _assess(rows).to_payload()
    assert report["accounting"]["filings"] == 9
    assert report["accounting"]["relevant_multi_label_issuers"] == 1
    assert report["accounting"]["relevant_multi_cik_labels"] == 2
    assert report["accounting"]["relevant_missing_label_filings"] == 1
    assert report["relevant_form_issuers"][1]["symbol_labels"] == ["NEW", "old"]
    selected = report["qualification_selector"]
    assert selected["first_lexical_single_label_unambiguous_association"] == {"issuer_cik": "0000000020", "raw_symbol_labels": ["SINGLE"]}
    assert selected["first_lexical_multi_label_issuer"] == {"issuer_cik": "0000000021", "raw_symbol_labels": ["NEW", "old"]}
    assert selected["first_lexical_nonplaceholder_multi_cik_label"] == {"raw_symbol_label": "DUP", "issuer_ciks": ["0000000022", "0000000023"]}
    assert selected["fixed_aapl_feasibility_only_not_representative"] == {"issuer_cik": "0000320193", "raw_symbol_labels": ["AAPL"]}
    assert selected["provider_symbols_inferred"] is selected["request_urls_constructed"] is selected["delisted_or_reused_status_inferred"] is False


def test_context_only_alias_does_not_create_relevant_issuer_or_selection():
    result = _assess([_row(1), _row(2, DOCUMENT_TYPE="3", ISSUERCIK="44", ISSUERTRADINGSYMBOL="ONLYCONTEXT")]).to_payload()
    assert result["accounting"]["all_form_issuers"] == 2
    assert result["accounting"]["relevant_issuers"] == 1
    assert result["qualification_selector"]["first_lexical_multi_label_issuer"] is None
    assert result["qualification_selector"]["first_lexical_nonplaceholder_multi_cik_label"] is None
    assert result["qualification_selector"]["fixed_aapl_feasibility_only_not_representative"] is None
    assert result["qualification_selector"]["missing_strata_dropped"] is False


def test_only_submission_member_opened(monkeypatch):
    raw = _zip()
    original = zipfile.ZipFile.open
    seen = []
    def guarded(self, name, *args, **kwargs):
        actual = name.filename if isinstance(name, zipfile.ZipInfo) else name
        seen.append(actual)
        assert actual == "SUBMISSION.tsv"
        return original(self, name, *args, **kwargs)
    monkeypatch.setattr(zipfile.ZipFile, "open", guarded)
    result = inventory.assess_earnings_issuer_inventory(raw, expected_archive_sha256=hashlib.sha256(raw).hexdigest())
    assert result.to_payload()["accounting"]["filings"] == 1
    assert seen == ["SUBMISSION.tsv"]


@pytest.mark.parametrize("change", [
    {"ISSUERCIK": "0"}, {"ISSUERCIK": "00000000000"}, {"ISSUERCIK": "１２３"},
    {"ISSUERCIK": "-12"}, {"ISSUERCIK": " 123"}, {"ISSUERCIK": ""},
    {"DOCUMENT_TYPE": "8-K"}, {"DOCUMENT_TYPE": "4 "}, {"DOCUMENT_TYPE": ""},
    {"ACCESSION_NUMBER": "wrong"}, {"FILING_DATE": "31-APR-2006"},
    {"FILING_DATE": "31-DEC-2005"}, {"FILING_DATE": "01-APR-2006"},
    {"FILING_DATE": "03-jan-2006"}, {"ISSUERTRADINGSYMBOL": "bad\x00label"},
    {"ISSUERTRADINGSYMBOL": "X" * 4097},
])
def test_malformed_row_refuses_entire_input_not_silent_dropping(change):
    with pytest.raises(inventory.EarningsIssuerInventoryError, match="REFUSED"):
        _assess([_row(1), _row(2, **change)])


@pytest.mark.parametrize("kwargs", [
    {"omit": "FOOTNOTES.tsv"}, {"extra": "../escape.tsv"}, {"extra": "nested/SUBMISSION.tsv"},
    {"duplicate": "SUBMISSION.tsv"}, {"headers": tuple(reversed(_headers()))},
    {"headers": _headers() + ("UNKNOWN",)}, {"raw_submission": b"\xff"},
    {"rows": []},
])
def test_exact_archive_and_schema_refuse_malformed_shapes(kwargs):
    with pytest.raises(inventory.EarningsIssuerInventoryError, match="REFUSED"):
        _assess(**kwargs)


def test_duplicate_accession_and_mixed_dialects_refuse():
    for rows in [[_row(1), _row(1)], [_row(1), _row(2, FILING_DATE="2006-01-04")]]:
        with pytest.raises(inventory.EarningsIssuerInventoryError):
            _assess(rows)


def test_iso_dates_and_accession_year_mismatch_retained():
    report = _assess([_row(FILING_DATE="2006-01-03", ACCESSION_NUMBER="0000000123-05-000001")]).to_payload()
    assert report["filing_date_dialect"] == "iso"
    assert report["accounting"]["accession_year_mismatches"] == 1
    assert report["filings"][0]["accession_year_mismatch"] is True
    assert report["filings"][0]["raw_issuer_cik"] == "123"
    assert report["filings"][0]["issuer_cik"] == "0000000123"


@pytest.mark.parametrize("raw", [b"", bytearray(b"zip"), "zip", b"not-a-zip"])
def test_archive_types_and_shape_refuse(raw):
    with pytest.raises(inventory.EarningsIssuerInventoryError):
        inventory.assess_earnings_issuer_inventory(raw, expected_archive_sha256="a" * 64)


def test_external_hash_change_refuses_before_zip_open(monkeypatch):
    raw = _zip()
    monkeypatch.setattr(zipfile, "ZipFile", lambda *_: pytest.fail("must refuse before decoding"))
    with pytest.raises(inventory.EarningsIssuerInventoryError, match="external_archive_hash"):
        inventory.assess_earnings_issuer_inventory(raw, expected_archive_sha256="a" * 64)


@pytest.mark.parametrize("digest", [None, True, 1, float("nan"), float("inf"), b"a" * 64, "A" * 64, "a" * 63])
def test_external_digest_requires_exact_finite_canonical_text(digest):
    with pytest.raises(inventory.EarningsIssuerInventoryError):
        inventory.assess_earnings_issuer_inventory(_zip(), expected_archive_sha256=digest)


def test_every_count_and_boolean_retains_exact_integer_and_boolean_types():
    report = _assess().to_payload()
    assert all(type(value) is int for key, value in report["accounting"].items() if key != "form_counts")
    assert all(type(value) is int for value in report["accounting"]["form_counts"].values())
    assert all(type(value) is bool and value is False for value in report["authority"].values())
    assert type(report["filings"][0]["source_record_ordinal"]) is int
    assert type(report["filings"][0]["relevant_form4_or_amendment"]) is bool


def test_determinism_and_detached_payload_cannot_alter_seal():
    raw = _zip()
    one = inventory.assess_earnings_issuer_inventory(raw, expected_archive_sha256=hashlib.sha256(raw).hexdigest())
    two = inventory.assess_earnings_issuer_inventory(raw, expected_archive_sha256=hashlib.sha256(raw).hexdigest())
    assert one.sha256 == two.sha256 == hashlib.sha256(one.canonical_bytes()).hexdigest()
    body = one.to_payload(); body["filings"].clear(); body["authority"]["backtesting_ready"] = True
    assert len(one.to_payload()["filings"]) == 1
    assert one.to_payload()["authority"]["backtesting_ready"] is False
    object.__setattr__(one, "_raw", b"{}")
    with pytest.raises(inventory.EarningsIssuerInventoryError, match="genuine_unchanged"):
        one.to_payload()
    with pytest.raises(inventory.EarningsIssuerInventoryError, match="genuine_unchanged"):
        inventory.EarningsIssuerInventory(two.canonical_bytes(), object()).canonical_bytes()


def test_exclusive_private_publication_never_overwrites_even_same_bytes(tmp_path):
    os.chmod(tmp_path, 0o700)
    value = _assess()
    directory = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        assert inventory.publish_inventory(value, private_directory_fd=directory) == value.sha256
        assert stat.S_IMODE((tmp_path / "inventory.json").stat().st_mode) == 0o600
        assert (tmp_path / "inventory.json").read_bytes() == value.canonical_bytes()
        with pytest.raises(inventory.EarningsIssuerInventoryError, match="exclusive_private"):
            inventory.publish_inventory(value, private_directory_fd=directory)
        assert (tmp_path / "inventory.json").read_bytes() == value.canonical_bytes()
    finally:
        os.close(directory)


@pytest.mark.parametrize("mode", [0o755, 0o777, 0o750])
def test_nonprivate_directory_refuses_before_publication(tmp_path, mode):
    os.chmod(tmp_path, mode)
    directory = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        with pytest.raises(inventory.EarningsIssuerInventoryError, match="private_owned"):
            inventory.publish_inventory(_assess(), private_directory_fd=directory)
        assert not (tmp_path / "inventory.json").exists()
    finally:
        os.close(directory)


def test_existing_symlink_and_hardlink_publication_names_are_never_followed(tmp_path):
    os.chmod(tmp_path, 0o700)
    elsewhere = tmp_path / "untouched"
    elsewhere.write_bytes(b"untouched")
    leaf = tmp_path / "inventory.json"
    directory = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        leaf.symlink_to(elsewhere)
        with pytest.raises(inventory.EarningsIssuerInventoryError):
            inventory.publish_inventory(_assess(), private_directory_fd=directory)
        assert elsewhere.read_bytes() == b"untouched"
        leaf.unlink(); os.link(elsewhere, leaf)
        with pytest.raises(inventory.EarningsIssuerInventoryError):
            inventory.publish_inventory(_assess(), private_directory_fd=directory)
        assert elsewhere.read_bytes() == b"untouched"
    finally:
        os.close(directory)


@pytest.mark.parametrize("fd", [True, None, "3", -1])
def test_invalid_directory_descriptor_types_refuse(fd):
    with pytest.raises(inventory.EarningsIssuerInventoryError):
        inventory.publish_inventory(_assess(), private_directory_fd=fd)


def test_postpublication_private_leaf_mode_change_is_typed_refusal(tmp_path, monkeypatch):
    os.chmod(tmp_path, 0o700)
    original = inventory._exclusive_json
    def corrupt_mode(directory, name, body):
        result = original(directory, name, body)
        os.chmod(name, 0o644, dir_fd=directory)
        return result
    monkeypatch.setattr(inventory, "_exclusive_json", corrupt_mode)
    directory = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        with pytest.raises(inventory.EarningsIssuerInventoryError, match="exclusive_private_publication"):
            inventory.publish_inventory(_assess(), private_directory_fd=directory)
    finally:
        os.close(directory)


@pytest.mark.parametrize("bound", ["MAX_ARCHIVE_BYTES", "MAX_SUBMISSION_BYTES", "MAX_TOTAL_EXPANDED_BYTES", "MAX_FILINGS", "MAX_FIELD_BYTES", "MAX_OUTPUT_BYTES"])
def test_every_resource_bound_fails_closed(monkeypatch, bound):
    monkeypatch.setattr(inventory, bound, 1)
    with pytest.raises(inventory.EarningsIssuerInventoryError):
        _assess([_row(1), _row(2)])
