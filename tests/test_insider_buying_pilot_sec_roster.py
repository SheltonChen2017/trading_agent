"""Invented outside-lane metadata images only; no actual source reads."""
from __future__ import annotations

import csv
from dataclasses import replace
import io
import json
import zipfile

import pytest

from research import insider_buying_pilot_sec_roster as m


def _zip(period, changes=None):
    changes = changes or {}
    profile = m.selector.pure.build_retained_82q_schema_profile_candidate()
    year,quarter = int(period[:4]),int(period[-1]);sink = io.BytesIO()
    with zipfile.ZipFile(sink,"w",compression=zipfile.ZIP_DEFLATED) as archive:
        for table in m.selector.pure.headers.ALLOWED_SEC_TABLES:
            names = profile.variant_for(table,year,quarter).headers
            text = io.StringIO(newline="");writer = csv.writer(text,delimiter="\t",lineterminator="\n")
            writer.writerow(names)
            if table == "SUBMISSION.tsv":
                for index,form in enumerate(m.FORMS,start=1):
                    row = dict.fromkeys(names,"")
                    row.update(ACCESSION_NUMBER=f"0000000001-{year%100:02d}-{index:06d}",DOCUMENT_TYPE=form,
                        FILING_DATE=f"01-{('JAN','APR','JUL','OCT')[quarter-1]}-{year}",ISSUERCIK="0000000001",
                        ISSUERNAME="INVENTED NOT MARKET EVIDENCE",ISSUERTRADINGSYMBOL="INVENTED")
                    if period == "2021Q1" and form == "4":row["ISSUERCIK"] = "123"
                    row.update(changes.get(form,{}))
                    writer.writerow([row[name] for name in names])
            elif table == "NONDERIV_TRANS.tsv":
                text.write("PRIVATE FINANCIAL SENTINEL MUST NEVER BE OPENED\n")
            archive.writestr(table,text.getvalue().encode())
        for name in (m.bulk._LEGACY_AUXILIARY_MEMBERS if year <= 2022 else m.bulk._CURRENT_AUXILIARY_MEMBERS):
            archive.writestr(name,b"opaque auxiliary")
    return sink.getvalue()


def _manifest(images):
    text = io.StringIO(newline="");writer = csv.writer(text,quoting=csv.QUOTE_ALL,lineterminator="\r\n")
    census = m.selector.pure.census
    writer.writerow(census._MANIFEST_HEADER)
    for item in images:
        writer.writerow((item.period,item.period.lower()+"_form345.zip",census._expected_url(item.period),
            len(item.raw_bytes),m._sha(item.raw_bytes),"2026-09-24T22:52:19.7647157Z",
            census._TIMESTAMP_BASIS,census._CAPTURE_COMMIT,census._SOURCE_INDEX_URL))
    return text.getvalue().encode()


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    # The actual reader takes bytes only. The sole filesystem fixture is an
    # invented temporary directory, never an alias of either real lane root.
    path = tmp_path_factory.mktemp("invented-pilot-sec-roster")
    assert m.selector.previous._fixture_fence(path) is None
    pure = m.selector.pure
    images = tuple(pure.QuarterArchive(period,_zip(period)) for period in pure._periods())
    manifest = _manifest(images);bindings = pure.census._manifest_bindings(manifest)
    profile = pure.build_retained_82q_schema_profile_candidate()
    quarters = tuple(pure.census._census_quarter(item.raw_bytes,binding) for item,binding in zip(images,bindings,strict=True))
    headers = tuple(pure.headers._quarter_headers(item.raw_bytes,item.period,profile) for item in images)
    census = pure._census_receipt(quarters,m._sha(manifest),len(manifest),True)
    header = pure._header_receipt(headers,census.sha256,True)
    selected = pure.select_affected_quarters(intake_manifest_raw=manifest,expected_manifest_sha256=m._sha(manifest),
        quarter_inputs=iter(images),expected_census_sha256=census.sha256,
        expected_header_preflight_sha256=header.sha256,fixture_only=True).to_payload()
    # Exercise the retained control's exact schema with invented bytes. The
    # new roster still marks the whole result fixture_only=True and cannot use
    # either production pin.
    selected["fixture_only"] = False
    return manifest,images,selected


def _args(corpus,consume=None):
    manifest,images,selected = corpus
    encoded = m._raw(selected)
    return dict(intake_manifest_raw=manifest,expected_manifest_sha256=m._sha(manifest),
        selection_raw=encoded,expected_selection_sha256=m._sha(encoded),
        quarter_inputs=iter(item for item in images if item.period in m.CONTEXT_PERIODS),
        consume_row=consume or (lambda row:None),fixture_only=True)


def _changed(corpus,period,transform):
    _,images,selected = corpus;images = list(images);selected = json.loads(m._raw(selected))
    index = next(i for i,item in enumerate(images) if item.period == period)
    old = images[index];source = zipfile.ZipFile(io.BytesIO(old.raw_bytes));sink = io.BytesIO()
    with source,zipfile.ZipFile(sink,"w",compression=zipfile.ZIP_DEFLATED) as target:
        for name in source.namelist():
            raw = source.read(name)
            target.writestr(name,transform(raw) if name == "SUBMISSION.tsv" else raw)
    raw = sink.getvalue();images[index] = m.selector.pure.QuarterArchive(period,raw)
    manifest = _manifest(images)
    row = selected["quarters"][index]
    member = zipfile.ZipFile(io.BytesIO(raw)).read("SUBMISSION.tsv")
    row.update(zip_sha256=m._sha(raw),zip_size_bytes=len(raw),submission_member_sha256=m._sha(member),
        submission_member_bytes=len(member),submission_header_line_sha256=m._sha(member.split(b"\n",1)[0]+b"\n"))
    selected.update(intake_manifest_sha256=m._sha(manifest),intake_manifest_bytes=len(manifest),
        quarters_sha256=m._sha(m._raw(selected["quarters"])))
    return manifest,tuple(images),selected


def _fields(raw,index,key,value):
    text = io.StringIO(raw.decode(),newline="");rows = list(csv.reader(text,delimiter="\t"))
    rows[index][rows[0].index(key)] = value
    output = io.StringIO(newline="");csv.writer(output,delimiter="\t",lineterminator="\n").writerows(rows)
    return output.getvalue().encode()


def test_complete_six_forms_exact_scope_raw_identity_hashes_and_callback_framing(corpus):
    rows = [];result = m.derive_pilot_sec_roster(**_args(corpus,rows.append));body = result.to_payload()
    assert len(rows) == 150 and len(body["quarters"]) == 25
    assert body["counts"] == {"context_quarters":25,"pilot_quarters":20,"context_submission_rows":150,
        "context_form4_or_4a_rows":50,"pilot_submission_rows":120,"pilot_form4_or_4a_rows":40}
    assert body["context_form_counts"] == dict.fromkeys(m.FORMS,25)
    assert body["pilot_form_counts"] == dict.fromkeys(m.FORMS,20)
    assert [row["source_record_ordinal"] for row in rows] == list(range(1,7))*25
    short = next(row for row in rows if row["period"] == "2021Q1" and row["form_type"] == "4")
    assert short["raw_issuer_cik"] == "123" and short["issuer_comparison_key"] == "0000000123"
    assert short["raw_filing_date"] == "01-JAN-2021" and short["filing_date"] == "2021-01-01"
    assert short["short_cik"] is True and short["accession_year_mismatch"] is False
    assert all(set(row) == m.ROW_KEYS and row["filing_metadata_sha256"] == m._sha(m._raw(
        {key:value for key,value in row.items() if key != "filing_metadata_sha256"})) for row in rows)
    raw = b"".join(m._raw(row)+b"\n" for row in rows)
    assert body["source_row_jsonl_sha256"] == m._sha(raw) and body["source_row_jsonl_bytes"] == len(raw)
    for quarter in body["quarters"]:
        selected = b"".join(m._raw(row)+b"\n" for row in rows if row["period"] == quarter["period"])
        assert quarter["source_row_jsonl_sha256"] == m._sha(selected)
        assert quarter["source_row_jsonl_bytes"] == len(selected)
    assert all(value is False or type(value) is int and value == 0 for value in body["authority"].values())
    assert b"INVENTED" not in result.canonical_bytes() and b"PRIVATE FINANCIAL" not in result.canonical_bytes()


def test_other_member_bodies_never_opened_or_numeric_values_interpreted(corpus,monkeypatch):
    original = zipfile.ZipFile.open
    def guarded(self,name,*args,**kwargs):
        assert (name.filename if hasattr(name,"filename") else name) == "SUBMISSION.tsv"
        return original(self,name,*args,**kwargs)
    monkeypatch.setattr(zipfile.ZipFile,"open",guarded)
    assert m.derive_pilot_sec_roster(**_args(corpus)).to_payload()["counts"]["context_quarters"] == 25


@pytest.mark.parametrize("fault",("manifest_hash","selection_hash","fixture_type","actual_mode","list",
    "missing","extra","reorder","wrong_period","bytearray","changed_zip","no_callback","invented_actual_pin"))
def test_input_anchors_types_source_order_exact_scope_and_fixture_boundary(corpus,fault):
    args = _args(corpus);items = list(args["quarter_inputs"]);args["quarter_inputs"] = iter(items)
    if fault == "manifest_hash":args["expected_manifest_sha256"] = "f"*64
    elif fault == "selection_hash":args["expected_selection_sha256"] = "f"*64
    elif fault == "fixture_type":args["fixture_only"] = 1
    elif fault == "actual_mode":args["fixture_only"] = False
    elif fault == "list":args["quarter_inputs"] = items
    elif fault == "no_callback":args["consume_row"] = None
    elif fault == "invented_actual_pin":args["expected_manifest_sha256"] = m.selector.pure.census.RETAINED_ZIP_MANIFEST_SHA256
    else:
        if fault == "missing":items.pop()
        elif fault == "extra":items.append(items[-1])
        elif fault == "reorder":items[0],items[1] = items[1],items[0]
        elif fault == "wrong_period":items[0] = m.selector.pure.QuarterArchive("2020Q2",items[0].raw_bytes)
        elif fault == "bytearray":items[0] = m.selector.pure.QuarterArchive(items[0].period,bytearray(items[0].raw_bytes))
        else:items[0] = m.selector.pure.QuarterArchive(items[0].period,items[0].raw_bytes+b"changed")
        args["quarter_inputs"] = iter(items)
    with pytest.raises(m.PilotSecRosterError):m.derive_pilot_sec_roster(**args)


@pytest.mark.parametrize("key,value,code",(
    ("ISSUERCIK","0","source_cik_lexical_shape_refused"),("ISSUERCIK","１２３","source_cik_lexical_shape_refused"),
    ("ISSUERCIK","12345678901","source_cik_lexical_shape_refused"),
    ("DOCUMENT_TYPE","4 / A","source_ownership_form_refused"),
    ("ACCESSION_NUMBER","not-an-accession","source_accession_invalid_or_duplicated"),
    ("ACCESSION_NUMBER","0000000001-21-000001","source_accession_invalid_or_duplicated"),
    ("FILING_DATE","01-APR-2021","source_filing_date_outside_quarter"),
    ("FILING_DATE","2021-01-01","source_filing_date_dialects_mixed"),
    ("FILING_DATE","31-FEB-2021","source_submission_decode_refused"),
    ("ISSUERTRADINGSYMBOL","bad\x01label","source_symbol_label_refused"),
    ("ISSUERTRADINGSYMBOL","x"*4097,"source_symbol_label_refused"),
))
def test_bad_metadata_never_silently_dropped_or_normalized(corpus,key,value,code):
    changed = _changed(corpus,"2021Q1",lambda raw:_fields(raw,3,key,value))
    with pytest.raises(m.PilotSecRosterError,match=code):m.derive_pilot_sec_roster(**_args(changed))


@pytest.mark.parametrize("fault",("header","ragged","member_hash","member_header","count","anomaly",
    "unknown_selection","bool_count","positive_authority"))
def test_profile_member_and_selector_accounting_contracts_are_binding(corpus,fault):
    if fault in {"header","ragged"}:
        def change(raw):
            if fault == "header":return raw.replace(b"ISSUERCIK",b"WRONGCIK",1)
            return raw+b"ragged\n"
        args = _args(_changed(corpus,"2021Q1",change))
    else:
        manifest,images,selected = corpus;selected = json.loads(m._raw(selected))
        row = next(item for item in selected["quarters"] if item["period"] == "2021Q1")
        if fault == "member_hash":row["submission_member_sha256"] = "f"*64
        elif fault == "member_header":row["submission_header_line_sha256"] = "f"*64
        elif fault == "count":row["submission_rows"] += 1
        elif fault == "anomaly":row["short_cik_rows"] = 0
        elif fault == "unknown_selection":selected["extra"] = True
        elif fault == "bool_count":selected["counts"]["quarters_scanned"] = True
        else:selected["authority"]["backtesting_ready"] = True
        selected["quarters_sha256"] = m._sha(m._raw(selected["quarters"]))
        args = _args((manifest,images,selected))
    with pytest.raises(m.PilotSecRosterError):m.derive_pilot_sec_roster(**args)


def test_callback_mutation_cannot_rewrite_summary_or_following_rows(corpus):
    rows = []
    def consumer(row):
        rows.append(json.loads(m._raw(row)))
        row.clear()
    body = m.derive_pilot_sec_roster(**_args(corpus,consumer)).to_payload()
    assert body["source_row_jsonl_sha256"] == m._sha(b"".join(m._raw(row)+b"\n" for row in rows))
    assert len(rows) == 150


@pytest.mark.parametrize("kind",("exception","return"))
def test_callback_refusals_have_safe_fixed_codes_and_no_completed_receipt(corpus,kind):
    def consume(row):
        if kind == "exception":raise ValueError("PRIVATE RAW PROVIDER TEXT")
        return True
    with pytest.raises(m.PilotSecRosterError) as caught:m.derive_pilot_sec_roster(**_args(corpus,consume))
    assert str(caught.value) == ("row_consumer_refused" if kind == "exception" else "row_consumer_must_return_none")


def test_factory_registry_seal_copies_and_exact_type_are_binding(corpus):
    result = m.derive_pilot_sec_roster(**_args(corpus))
    payload = result.to_payload();payload["authority"]["backtesting_ready"] = True
    assert result.to_payload()["authority"]["backtesting_ready"] is False
    with pytest.raises(m.PilotSecRosterError):replace(result).to_payload()
    with pytest.raises(m.PilotSecRosterError):m.validate_pilot_sec_roster(payload)
    object.__setattr__(result,"_bytes",m._raw(payload))
    with pytest.raises(m.PilotSecRosterError):result.to_payload()


def test_output_limits_are_refusals_not_truncation(corpus,monkeypatch):
    monkeypatch.setattr(m,"MAX_RESULT_BYTES",1)
    with pytest.raises(m.PilotSecRosterError,match="roster_summary_output_bound_refused"):
        m.derive_pilot_sec_roster(**_args(corpus))


def test_held_generator_refuses_arbitrary_loader_or_hold(corpus):
    with pytest.raises(m.PilotSecRosterError,match="exact_existing_intake_hold_required"):
        list(m.held_context_quarters(object()))


def _invented_hold(corpus):
    manifest,images,_ = corpus
    class Tree:
        checks = 0
        handles = [(item.period.lower()+"_form345.zip",io.BytesIO(item.raw_bytes),None,len(item.raw_bytes))
            for item in images]
        def check(self):self.checks += 1
    held = object.__new__(m.selector._HeldIntake)
    held.bindings = m.selector.pure.census._manifest_bindings(manifest)
    held.tree = Tree()
    return held


def test_held_generator_filters_context_once_without_rehashing_other_archives(corpus,monkeypatch):
    held = _invented_hold(corpus)
    def no_full_recheck(*args):pytest.fail("per-quarter full84leaf rehash is not allowed")
    monkeypatch.setattr(m.selector._HeldIntake,"recheck",no_full_recheck)
    result = list(m.held_context_quarters(held))
    assert tuple(item.period for item in result) == m.CONTEXT_PERIODS
    assert held.tree.checks == 50
    assert all(type(item) is m.selector.pure.QuarterArchive for item in result)


@pytest.mark.parametrize("kind",("bytes","size","missing","periods"))
def test_held_generator_keeps_exact_inventory_hash_size_and_period_guards(corpus,kind):
    held = _invented_hold(corpus)
    index = next(i for i,item in enumerate(held.tree.handles) if item[0] == "2020q1_form345.zip")
    held.tree.handles = list(held.tree.handles)
    name,stream,version,cap = held.tree.handles[index]
    if kind == "bytes":held.tree.handles[index] = (name,io.BytesIO(b"x"*cap),version,cap)
    elif kind == "size":held.tree.handles[index] = (name,stream,version,cap-1)
    elif kind == "missing":held.tree.handles.pop(index)
    else:held.bindings = held.bindings[:-1]
    with pytest.raises(m.PilotSecRosterError):list(m.held_context_quarters(held))


@pytest.mark.parametrize("period",("2022Q4","2023Q1"))
def test_auxiliary_names_follow_existing_era_contract_and_wrong_era_refuses(corpus,period):
    manifest,images,_ = corpus
    binding = next(item for item in m.selector.pure.census._manifest_bindings(manifest) if item.period == period)
    raw = next(item.raw_bytes for item in images if item.period == period)
    assert m._submission_bytes(raw,binding).startswith(b"ACCESSION_NUMBER")
    source = zipfile.ZipFile(io.BytesIO(raw));target = io.BytesIO()
    old,new = ((m.bulk._LEGACY_AUXILIARY_MEMBERS,m.bulk._CURRENT_AUXILIARY_MEMBERS) if period == "2022Q4"
        else (m.bulk._CURRENT_AUXILIARY_MEMBERS,m.bulk._LEGACY_AUXILIARY_MEMBERS))
    rename = dict(zip(old,new,strict=True))
    with source,zipfile.ZipFile(target,"w",compression=zipfile.ZIP_DEFLATED) as output:
        for name in source.namelist():output.writestr(rename.get(name,name),source.read(name))
    with pytest.raises(m.PilotSecRosterError,match="source_era_member_inventory_refused"):
        m._submission_bytes(target.getvalue(),binding)


def test_null_submission_and_wrong_crc_are_safe_refusals(corpus):
    manifest,images,_ = corpus
    binding = next(item for item in m.selector.pure.census._manifest_bindings(manifest) if item.period == "2021Q1")
    raw = next(item.raw_bytes for item in images if item.period == "2021Q1")
    source = zipfile.ZipFile(io.BytesIO(raw));target = io.BytesIO()
    with source,zipfile.ZipFile(target,"w",compression=zipfile.ZIP_DEFLATED) as output:
        for name in source.namelist():
            value = source.read(name)
            output.writestr(name,value+b"\x00" if name == "SUBMISSION.tsv" else value)
    with pytest.raises(m.PilotSecRosterError,match="submission_length_or_crc_refused"):
        m._submission_bytes(target.getvalue(),binding)
