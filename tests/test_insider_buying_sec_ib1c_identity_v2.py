"""Invented v2 identities only; no source acquisition or evidence promotion."""
from dataclasses import replace

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.insider_buying import sec_ib1c_identity_v2 as module
from research.insider_buying.sec_bulk_parsed_snapshot import (
    LoadedSecBulkParsedSnapshot, ParsedSecBulkAccession, ParsedSecBulkRow, _source_row_id,
)
from research.insider_buying.sec_complete_submission import project_sec_complete_submission
from test_insider_buying_sec_complete_submission import _complete, _target
from test_insider_buying_sec_master_locator_reconciliation import _snapshot, _census


def _inputs(specs=(("4", "2023-01-15", "123456", "23"),), *, ordinals=None):
    base = _snapshot("2023Q1")
    rows, summaries = [], []
    for offset, (form, raw_date, cik, year) in enumerate(specs):
        ordinal = offset + 1 if ordinals is None else ordinals[offset]
        accession = f"0000123456-{year}-{offset + 1:06d}"
        values = (accession, raw_date, "2023-01-15", form, cik, "Invented", "INVT")
        row_id = _source_row_id(
            raw_snapshot_id=base.identity.raw_snapshot_id,
            raw_lineage_hash=base.identity.raw_lineage_hash,
            raw_archive_sha256=base.identity.raw_archive_sha256,
            table_name="SUBMISSION.tsv", raw_member_sha256="b" * 64,
            source_record_ordinal=ordinal, values=values, source_row_key=(),
        )
        rows.append(ParsedSecBulkRow("SUBMISSION.tsv", "submission", ordinal, accession, values, (), row_id))
        summaries.append(ParsedSecBulkAccession(accession, form, row_id, (("SUBMISSION.tsv", (row_id,)),)))
    table = replace(base.identity.tables[0], row_count=len(rows), row_ids_hash=hash_payload([row.row_id for row in rows]))
    identity = replace(base.identity, tables=(table, *base.identity.tables[1:]), lineage_hash="", snapshot_id="")
    lineage = hash_payload(identity.lineage_payload())
    identity = replace(identity, lineage_hash=lineage, snapshot_id=f"sec-insider-parsed-2023q1-{lineage[:16]}")
    census = next(q for q in _census().quarters if q.period == "2023Q1")
    census = replace(census, form_counts=tuple(sum(s[0] == form for s in specs) for form in ("3", "3/A", "4", "4/A", "5", "5/A")))
    return LoadedSecBulkParsedSnapshot(identity, tuple(rows), tuple(summaries)), census


def _parent(source, *, cik=None, form=None, filed="2023-01-15"):
    raw_cik = source.values[4].zfill(10) if cik is None else cik
    form = source.values[3] if form is None else form
    target = replace(_target(), period="2023Q1", accession_number=source.accession_number,
                     form_type=form, filing_date=filed, issuer_cik=raw_cik,
                     complete_submission_url="https://www.sec.gov/Archives/edgar/data/888888/" + source.accession_number + ".txt")
    raw = (_complete().replace(b"0000999999-22-000001", source.accession_number.encode())
           .replace(b"20221107", filed.replace("-", "").encode())
           .replace(b"<CIK>0000123456", b"<CIK>" + raw_cik.encode())
           .replace(b"<issuerCik>0000123456", b"<issuerCik>" + raw_cik.encode())
           .replace(b"<TYPE>4\n", f"<TYPE>{form}\n".encode())
           .replace(b"<documentType>4</documentType>", f"<documentType>{form}</documentType>".encode()))
    return project_sec_complete_submission(target, raw)


def test_raw_short_cik_and_year_mismatch_require_reparsed_corroboration():
    snapshot, census = _inputs((("4", "15-JAN-2023", "123456", "22"),))
    without = module.assess_ib1c_v2_quarter_identity(snapshot, census).to_payload()
    assert without["submission_count"] == without["quarantined_count"] == 1
    assert without["whole_quarter_identity_sha256"] is None
    parent = _parent(snapshot.rows[0])
    result = module.assess_ib1c_v2_quarter_identity(snapshot, census, (parent,))
    body = result.to_payload()
    row = body["rows"][0]
    assert row["raw_issuer_cik"] == "123456" and row["issuer_comparison_key"] == "0000123456"
    assert row["raw_filing_date"] == "15-JAN-2023" and row["accession_year_mismatch"] is True
    assert row["short_cik"] is True and row["disposition"] == "corroborated_noncanonical"
    assert body["quarantined_count"] == 0 and body["whole_quarter_identity_sha256"]
    assert row["corroboration"]["projection_sha256"] == parent.sha256
    assert all(value is False or type(value) is int and value == 0 for value in body["authority"].values())
    assert result.sha256 == hash_payload(body)


def test_all_six_forms_are_accounted_without_silent_narrowing():
    specs = tuple((form, "2023-01-15", "123456", "23") for form in ("3", "3/A", "4", "4/A", "5", "5/A"))
    snapshot, census = _inputs(specs)
    parents = tuple(_parent(row) for row in snapshot.rows if row.values[3] in {"4", "4/A"})
    body = module.assess_ib1c_v2_quarter_identity(snapshot, census, parents).to_payload()
    assert body["submission_count"] == 6 and body["corroborated_count"] == 2
    assert body["quarantined_count"] == 4 and body["whole_quarter_identity_sha256"] is None
    assert [row["form_type"] for row in body["rows"]] == [s[0] for s in specs]
    assert all(row["quarantine_reasons"] == ["unsupported_parent_corroboration_form"] for row in body["rows"] if row["form_type"] not in {"4", "4/A"})


@pytest.mark.parametrize("changes", [{"cik": "0000123457"}, {"form": "4/A"}, {"filed": "2023-01-16"}])
def test_cross_source_identity_conflict_is_quarantined(changes):
    snapshot, census = _inputs()
    body = module.assess_ib1c_v2_quarter_identity(snapshot, census, (_parent(snapshot.rows[0], **changes),)).to_payload()
    assert body["rows"][0]["quarantine_reasons"] == ["complete_parent_identity_conflict"]
    assert body["whole_quarter_identity_sha256"] is None


@pytest.mark.parametrize("cik", ["0", "0000000000", "１２３", "+123", "12345678901", " 123", ""])
@pytest.mark.parametrize("form", ["4", "3"])
def test_invalid_raw_issuer_cik_is_refused_in_every_form(cik, form):
    snapshot, census = _inputs(((form, "2023-01-15", cik, "23"),))
    with pytest.raises(module.Ib1cIdentityV2Error):
        module.assess_ib1c_v2_quarter_identity(snapshot, census)


@pytest.mark.parametrize("raw_date", ["2023-02-30", "2022-12-31", "15-jan-2023", "20230115", "2023-1-15"])
def test_invalid_or_out_of_quarter_date_refused(raw_date):
    snapshot, census = _inputs((("3", raw_date, "123456", "23"),))
    with pytest.raises(module.Ib1cIdentityV2Error):
        module.assess_ib1c_v2_quarter_identity(snapshot, census)


def test_mixed_date_dialects_and_reordered_ordinals_refused():
    snapshot, census = _inputs((("4", "2023-01-15", "123456", "23"), ("4", "15-JAN-2023", "123456", "23")))
    with pytest.raises(module.Ib1cIdentityV2Error):
        module.assess_ib1c_v2_quarter_identity(snapshot, census)
    snapshot, census = _inputs(ordinals=(2,))
    with pytest.raises(module.Ib1cIdentityV2Error):
        module.assess_ib1c_v2_quarter_identity(snapshot, census)


def test_parent_duplicates_extra_inputs_and_derived_byte_tampering_refused():
    snapshot, census = _inputs()
    parent = _parent(snapshot.rows[0])
    for parents in ((parent, parent), [parent], (parent,) * 257):
        with pytest.raises(module.Ib1cIdentityV2Error):
            module.assess_ib1c_v2_quarter_identity(snapshot, census, parents)
    with pytest.raises(module.Ib1cIdentityV2Error):
        module.assess_ib1c_v2_quarter_identity(snapshot, census, (project_sec_complete_submission(_target(), _complete()),))
    object.__setattr__(parent, "raw_bytes", parent.raw_bytes.replace(b"<CIK>0000123456", b"<CIK>0000123457"))
    with pytest.raises(module.Ib1cIdentityV2Error):
        module.assess_ib1c_v2_quarter_identity(snapshot, census, (parent,))


def test_byte_bound_and_source_lineage_mutation_refused(monkeypatch):
    snapshot, census = _inputs()
    monkeypatch.setattr(module, "MAX_CORROBORATING_BYTES", 1)
    with pytest.raises(module.Ib1cIdentityV2Error):
        module.assess_ib1c_v2_quarter_identity(snapshot, census, (_parent(snapshot.rows[0]),))
    with pytest.raises(module.Ib1cIdentityV2Error):
        module.assess_ib1c_v2_quarter_identity(replace(snapshot, rows=()), census)
    object.__setattr__(census, "form_counts", (False, 0, 1, 0, 0, 0))
    with pytest.raises(module.Ib1cIdentityV2Error):
        module.assess_ib1c_v2_quarter_identity(snapshot, census)


def test_payload_copy_cannot_alter_result_and_reconstruction_cannot_grant_authority():
    snapshot, census = _inputs()
    result = module.assess_ib1c_v2_quarter_identity(snapshot, census)
    body = result.to_payload()
    body["authority"]["backtest_authorized"] = True
    assert result.to_payload()["authority"]["backtest_authorized"] is False
    raw = canonical_json(body).encode()
    forged = replace(result, _canonical_bytes=raw, _digest=hash_bytes(raw))
    with pytest.raises(module.Ib1cIdentityV2Error):
        forged.to_payload()


def test_empty_quarter_does_not_emit_identity_completeness():
    snapshot, census = _inputs(())
    body = module.assess_ib1c_v2_quarter_identity(snapshot, census).to_payload()
    assert body["submission_count"] == 0
    assert body["whole_quarter_identity_sha256"] is None
