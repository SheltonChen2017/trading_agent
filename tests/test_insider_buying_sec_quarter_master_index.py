"""Synthetic, zero-I/O tests for the quarterly EDGAR master-index boundary."""
from __future__ import annotations

import pytest

from data.hashing import hash_bytes, hash_payload
from research.insider_buying import sec_quarter_master_index as module
from research.insider_buying.sec_quarter_master_index import (
    SecMasterIndexExpectedRow,
    SecQuarterMasterIndexError,
    join_exact_sec_master_inventory,
    parse_sec_quarter_master_index,
    select_sec_master_index_subset,
)


_HEADER = (
    b"Description: Master Index of EDGAR Dissemination Feed\n"
    b"Last Data Received: March 31, 2023\n"
    b"Comments: webmaster@sec.gov\n"
    b"\n"
    b"CIK|Company Name|Form Type|Date Filed|Filename\n"
    b"--------------------------------------------------------------------------------\n"
)
_FOUR = (
    b"1001|Example One Inc|4|2023-02-10|"
    b"edgar/data/987654/0000001001-23-000003.txt\n"
)
_AMENDMENT = (
    b"1002|Example Two Inc|4/A|2023-03-31|"
    b"edgar/data/1002/0000001002-23-000004.txt\n"
)
_OTHER = (
    b"1003|Example Three Inc|8-K|2023-01-01|"
    b"edgar/data/1003/0000001003-23-000005.txt\n"
)
_EXPECTED = (
    SecMasterIndexExpectedRow("0000001001-23-000003", "4", "2023-02-10"),
    SecMasterIndexExpectedRow("0000001002-23-000004", "4/A", "2023-03-31"),
)


def _parse(*body: bytes):
    return parse_sec_quarter_master_index(_HEADER + b"".join(body), year=2023, quarter=1)


def test_exact_index_path_is_retained_even_when_archive_cik_differs_from_index_cik():
    raw = _HEADER + _OTHER + _AMENDMENT + _FOUR
    receipt = parse_sec_quarter_master_index(raw, year=2023, quarter=1)
    assert receipt.source_sha256 == hash_bytes(raw)
    assert receipt.source_size_bytes == len(raw)
    assert receipt.all_filing_row_count == 3
    assert tuple(row.accession_number for row in receipt.rows) == tuple(
        item.accession_number for item in _EXPECTED
    )
    assert receipt.rows[0].archive_path == "edgar/data/987654/0000001001-23-000003.txt"
    assert receipt.receipt_sha256 == receipt.to_payload()["receipt_sha256"]
    assert join_exact_sec_master_inventory(receipt, _EXPECTED) == receipt.rows


def test_subset_is_explicitly_weaker_than_full_quarter_join():
    receipt = _parse(_FOUR, _AMENDMENT)
    assert select_sec_master_index_subset(receipt, (_EXPECTED[0],)) == (receipt.rows[0],)
    with pytest.raises(SecQuarterMasterIndexError, match="extra Form 4"):
        join_exact_sec_master_inventory(receipt, (_EXPECTED[0],))


def test_requested_order_is_preserved_without_creating_archive_paths():
    receipt = _parse(_FOUR, _AMENDMENT)
    assert select_sec_master_index_subset(receipt, tuple(reversed(_EXPECTED))) == tuple(
        reversed(receipt.rows)
    )


@pytest.mark.parametrize(
    "expected,message",
    (
        ((_EXPECTED[0],), "extra Form 4"),
        ((_EXPECTED[0], SecMasterIndexExpectedRow("0000001004-23-000006", "4", "2023-02-10")), "missing requested"),
        ((_EXPECTED[0], _EXPECTED[0]), "repeats an accession"),
        ((SecMasterIndexExpectedRow(_EXPECTED[0].accession_number, "4/A", _EXPECTED[0].filing_date), _EXPECTED[1]), "contradicts requested"),
        ((SecMasterIndexExpectedRow(_EXPECTED[0].accession_number, "4", "2023-02-11"), _EXPECTED[1]), "contradicts requested"),
    ),
)
def test_exact_join_refuses_missing_extra_duplicate_form_and_date(expected, message):
    with pytest.raises(SecQuarterMasterIndexError, match=message):
        join_exact_sec_master_inventory(_parse(_FOUR, _AMENDMENT), expected)


@pytest.mark.parametrize(
    "raw,message",
    (
        (_HEADER.replace(b"CIK|Company Name|Form Type|Date Filed|Filename", b"CIK|Company Name|Date Filed|Filename"), "columns are absent"),
        (_HEADER.replace(b"Description: Master Index", b"Description: Daily Index"), "description is not master"),
        (_HEADER.replace(b"Comments: webmaster@sec.gov\n", b"Comments: webmaster@sec.gov\nComments: duplicate\n"), "preamble keys"),
        (_HEADER.replace(b"--------------------------------------------------------------------------------", b"========"), "divider"),
        (_HEADER.replace(b"\n\nCIK", b"\n\n\nCIK"), "preamble"),
        (b"\xef\xbb\xbf" + _HEADER, "envelope"),
        (_HEADER.replace(b"\n", b"\r\n", 1), "mixes newline"),
    ),
)
def test_header_and_envelope_refusals(raw, message):
    with pytest.raises(SecQuarterMasterIndexError, match=message):
        parse_sec_quarter_master_index(raw + _FOUR, year=2023, quarter=1)


@pytest.mark.parametrize(
    "bad_row,message",
    (
        (b"1001|Example|4|2023-02-10|edgar/data/1001/0000001001-23-000003.txt|tail\n", "field count"),
        (b"1001|Example|4|2023-02-30|edgar/data/1001/0000001001-23-000003.txt\n", "filing date is invalid"),
        (b"1001|Example|4|2023-04-01|edgar/data/1001/0000001001-23-000003.txt\n", "outside quarter"),
        (b"1001|Example|4|2023-02-10|edgar/data/1001/0000001001-23-000003.txt\n", "repeats an accession"),
        (b"1001|Example|4|2023-02-10|edgar/data/../0000001001-23-000003.txt\n", "archive path is malformed"),
        (b"1001|Example|4|2023-02-10|https://www.sec.gov/Archives/edgar/data/1001/0000001001-23-000003.txt\n", "archive path is malformed"),
        (b"1001|Example|4|2023-02-10|edgar/data/1001/0000001001-23-000003.xml\n", "archive path is malformed"),
        (b"1001|Example\x00|4|2023-02-10|edgar/data/1001/0000001001-23-000003.txt\n", "control bytes"),
        (b"1001|Example|4/a|2023-02-10|edgar/data/1001/0000001001-23-000003.txt\n", "row fields are malformed"),
    ),
)
def test_malformed_body_refuses_entire_quarter(bad_row, message):
    with pytest.raises(SecQuarterMasterIndexError, match=message):
        _parse(_FOUR, bad_row)


def test_duplicate_accession_across_forms_refuses_before_filtering():
    other_form_same_accession = (
        b"1001|Example|8-K|2023-02-10|edgar/data/1001/0000001001-23-000003.txt\n"
    )
    with pytest.raises(SecQuarterMasterIndexError, match="repeats an accession or path"):
        _parse(_FOUR, other_form_same_accession)


@pytest.mark.parametrize("near_form", (b"4 ", b"4/A ", b"4 /A", b"4  / A"))
def test_near_form4_spelling_cannot_be_silently_dropped(near_form):
    row = (
        b"1002|Example|" + near_form + b"|2023-02-10|"
        b"edgar/data/1002/0000001002-23-000004.txt\n"
    )
    with pytest.raises(SecQuarterMasterIndexError, match="Form 4 spelling"):
        _parse(_FOUR, row)


def test_other_form_with_legitimate_embedded_space_is_not_near_form4():
    row = (
        b"1002|Example|SC 13D/A|2023-02-10|"
        b"edgar/data/1002/0000001002-23-000004.txt\n"
    )
    assert _parse(_FOUR, row).rows[0].accession_number == _EXPECTED[0].accession_number


def test_crlf_and_nonascii_company_are_accepted_but_raw_bytes_stay_distinct():
    lf = _HEADER + _FOUR
    crlf = lf.replace(b"Example One Inc", b"Caf\xe9 Inc").replace(b"\n", b"\r\n")
    receipt = parse_sec_quarter_master_index(crlf, year=2023, quarter=1)
    assert receipt.rows[0].archive_path == "edgar/data/987654/0000001001-23-000003.txt"
    assert receipt.source_sha256 != hash_bytes(lf)


def test_input_byte_and_row_caps_refuse_before_population(monkeypatch):
    monkeypatch.setattr(module, "MAX_MASTER_INDEX_BYTES", len(_HEADER + _FOUR) - 1)
    with pytest.raises(SecQuarterMasterIndexError, match="byte budget"):
        _parse(_FOUR)
    monkeypatch.setattr(module, "MAX_MASTER_INDEX_BYTES", 64 * 1024 * 1024)
    monkeypatch.setattr(module, "MAX_MASTER_INDEX_ROWS", 1)
    with pytest.raises(SecQuarterMasterIndexError, match="row count"):
        _parse(_FOUR, _AMENDMENT)


def test_pathological_newline_count_refuses_before_line_vector_split(monkeypatch):
    monkeypatch.setattr(module, "MAX_MASTER_INDEX_ROWS", 1)
    # This is small in the test; production allows up to 64 MiB, where
    # splitting an unbounded newline population could exhaust memory.
    many_lines = _HEADER + b"\n" * 10_000
    with pytest.raises(SecQuarterMasterIndexError, match="pre-split line count"):
        parse_sec_quarter_master_index(many_lines, year=2023, quarter=1)


@pytest.mark.parametrize(
    "row",
    (
        b"0000|Example|4|2023-02-10|edgar/data/987654/0000001001-23-000003.txt\n",
        b"1001|Example|4|2023-02-10|edgar/data/0000/0000001001-23-000003.txt\n",
    ),
)
def test_zero_filer_or_archive_cik_refuses(row):
    with pytest.raises(SecQuarterMasterIndexError, match="CIK|archive path"):
        _parse(row)


def test_direct_row_cannot_admit_zero_archive_cik():
    with pytest.raises(SecQuarterMasterIndexError, match="archive path"):
        module.SecMasterIndexRow(
            accession_number="0000001001-23-000003", form_type="4",
            filing_date="2023-02-10",
            archive_path="edgar/data/0000/0000001001-23-000003.txt",
        )


def test_receipt_mutation_is_refused_before_subset_lookup():
    receipt = _parse(_FOUR)
    object.__setattr__(receipt, "source_sha256", "0" * 64)
    with pytest.raises(SecQuarterMasterIndexError, match="fingerprint mismatch"):
        select_sec_master_index_subset(receipt, (_EXPECTED[0],))


def test_coherently_rehashed_unsafe_row_is_refused_before_subset_lookup():
    receipt = _parse(_FOUR)
    object.__setattr__(receipt.rows[0], "archive_path", "edgar/data/../bad.txt")
    object.__setattr__(receipt, "receipt_sha256", hash_payload(receipt._identity_payload()))
    with pytest.raises(SecQuarterMasterIndexError, match="archive path contradicts"):
        select_sec_master_index_subset(receipt, (_EXPECTED[0],))


def test_filing_date_and_expected_type_boundaries():
    with pytest.raises(SecQuarterMasterIndexError, match="expected filing date is invalid"):
        SecMasterIndexExpectedRow(_EXPECTED[0].accession_number, "4", "2023-02-30")
    with pytest.raises(SecQuarterMasterIndexError, match="expected accession tuple"):
        SecMasterIndexExpectedRow(_EXPECTED[0].accession_number, "4/a", "2023-02-10")
    with pytest.raises(SecQuarterMasterIndexError, match="expected inventory row type"):
        select_sec_master_index_subset(_parse(_FOUR), (object(),))
    with pytest.raises(SecQuarterMasterIndexError, match="outside quarter"):
        select_sec_master_index_subset(
            _parse(_FOUR),
            (SecMasterIndexExpectedRow(_EXPECTED[0].accession_number, "4", "2023-04-01"),),
        )
