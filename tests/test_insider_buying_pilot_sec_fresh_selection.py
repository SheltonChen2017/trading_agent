"""Invented 82-image fixtures; fresh pilot selection has no transport API."""
from copy import deepcopy
from dataclasses import replace
import csv
import importlib.util
import io
from pathlib import Path
from types import SimpleNamespace
import zipfile

import pytest

from research import insider_buying_pilot_sec_fresh_selection as m
from research.insider_buying.sec_quarter_master_index import parse_sec_quarter_master_index


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    spec = importlib.util.spec_from_file_location("invented_fresh_pilot_roster_fixture",
        Path(__file__).with_name("test_insider_buying_pilot_sec_roster.py"))
    helper = importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    original = helper._zip
    def expanded(period, changes=None):
        unique = {form: {"ACCESSION_NUMBER": f"0000000001-{int(period[:4])%100:02d}-{int(period[-1])*100000+index:06d}"}
            for index, form in enumerate(m.audit.FORMS, 1)}
        raw = original(period, unique)
        if period != m.PERIOD: return raw
        output = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(raw)) as source, zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as target:
            for name in source.namelist():
                data = source.read(name)
                if name == "SUBMISSION.tsv":
                    rows = list(csv.reader(io.StringIO(data.decode(), newline=""), delimiter="\t"))
                    headers = rows[0]
                    for index in range(7, 77):
                        item = dict(zip(headers, rows[3], strict=True))
                        item.update(ACCESSION_NUMBER=f"0000000001-21-{100000+index:06d}", DOCUMENT_TYPE="4/A" if index % 2 else "4",
                            ISSUERCIK="123", ISSUERTRADINGSYMBOL="INVENTED")
                        rows.append([item[field] for field in headers])
                    text = io.StringIO(newline="")
                    csv.writer(text, delimiter="\t", lineterminator="\n").writerows(rows)
                    data = text.getvalue().encode()
                target.writestr(name, data)
        return output.getvalue()
    helper._zip = expanded
    supplied = helper.corpus.__wrapped__(tmp_path_factory)
    rows = []
    generated = m.roster.derive_pilot_sec_roster(**helper._args(supplied, rows.append))
    return helper, supplied, generated, rows


def _master(period, rows, *, omit=()):
    header = b"Description: Master Index of EDGAR Dissemination Feed\n\nCIK|Company Name|Form Type|Date Filed|Filename\n--------------------------------------------------------------------------------\n"
    lines = [f"1|INVENTED|{row['form_type']}|{row['filing_date']}|edgar/data/999/{row['accession_number']}.txt\n".encode()
        for row in rows if row["period"] == period and row["form_type"] in {"4", "4/A"} and row["accession_number"] not in omit]
    if not lines:
        lines = [f"1|INVENTED|8-K|{period[:4]}-{(int(period[-1])-1)*3+1:02d}-01|edgar/data/1/0000000001-{int(period[:4])%100:02d}-999999.txt\n".encode()]
    return parse_sec_quarter_master_index(header + b"".join(lines), year=int(period[:4]), quarter=int(period[-1]))


def _pipeline(corpus, *, consumed=(), omit=(), mutate=None, supplied=None):
    helper, original, _unused, all_rows = corpus
    supplied = original if supplied is None else supplied
    if supplied is not original:
        all_rows = []
        m.roster.derive_pilot_sec_roster(**helper._args(supplied, all_rows.append))
    exposures = {"schema": m.audit.EXPOSURE_SCHEMA, "records": sorted([
        {"accession_number": row["accession_number"], "accession_key_sha256": row["accession_key_sha256"],
            "evidence": [{"root_id": "invented-root", "journal_sha256": "a" * 64, "state": state}]}
        for row, state in consumed], key=lambda row: row["accession_number"])}
    candidates = {"schema": m.audit.CANDIDATE_SCHEMA, "fixture_only": True, "records": [], "masters": [],
        "authority": dict(m.audit._AUTHORITY)}
    exposed_raw, candidates_raw = m._raw(exposures), m._raw(candidates)
    builder, emitted = m.PilotSecFreshSelectionBuilder(), []
    def consume(disposition):
        supplied_disposition = deepcopy(disposition)
        if mutate is not None: mutate(supplied_disposition)
        assert builder.consume(supplied_disposition) is None
        emitted.append(disposition)
    compiler = m.audit.PilotSecParentAuditCompiler(exposure_raw=exposed_raw, expected_exposure_sha256=m._sha(exposed_raw),
        candidates_raw=candidates_raw, expected_candidates_sha256=m._sha(candidates_raw),
        master_for_period=lambda period: _master(period, all_rows, omit=omit), emit_row=consume)
    generated = m.roster.derive_pilot_sec_roster(**helper._args(supplied, compiler.consume))
    completed = compiler.finish(generated)
    return builder, generated, completed, emitted


def _finish(pipeline, **changes):
    builder, source, completed, _ = pipeline
    arguments = {"roster": source, "audit": completed,
        "expected_roster_sha256": source.sha256, "expected_audit_sha256": completed.sha256}
    arguments.update(changes)
    return builder.finish(**arguments)


def _pilot_targets(corpus):
    return [row for row in corpus[3] if row["period"] == m.PERIOD and row["form_type"] in {"4", "4/A"}]


def _reframe(payload):
    requests = b"".join(m._raw(row["request"]) + b"\n" for row in payload["requests"])
    metadata = b"".join(m._raw(row) + b"\n" for row in payload["requests"])
    payload.update(selected_request_jsonl_sha256=m._sha(requests), selected_request_jsonl_bytes=len(requests),
        selected_metadata_jsonl_sha256=m._sha(metadata), selected_metadata_jsonl_bytes=len(metadata))


def test_completed_full_context_selects_first64_pilot_not_context_preview(corpus):
    pipeline = _pipeline(corpus)
    selected = _finish(pipeline)
    assert m.validate_pilot_sec_fresh_selection(selected) is selected
    body = selected.to_payload();targets = _pilot_targets(corpus)
    assert len(targets) == body["selection_period_observed_fresh_count"] == 72
    assert body["selection_period_eligible_after_global_suppression_count"] == 72
    assert body["selection_period_suppressed_late_repeat_count"] == 0
    assert [row["request"]["accession_number"] for row in body["requests"]] == [row["accession_number"] for row in targets[:64]]
    assert all(row["request"]["period"] == "2021Q1" for row in body["requests"])
    assert pipeline[2].to_payload()["fresh_request_preview"][0]["request"]["period"] == "2020Q1"
    assert body["source_roster_sha256"] == pipeline[1].sha256 and body["parent_audit_sha256"] == pipeline[2].sha256
    assert body["source_roster_counts"]["context_quarters"] == len(body["quarter_bindings"]) == 25
    assert body["source_roster_counts"]["pilot_quarters"] == 20
    assert body["parent_context_counts"] == pipeline[2].to_payload()["context_counts"]
    assert body["parent_pilot_counts"] == pipeline[2].to_payload()["pilot_counts"]
    assert body["full_disposition_jsonl_sha256"] == m._sha(b"".join(m._raw(row) + b"\n" for row in pipeline[3]))
    assert m.validate_selection_payload(body) == body
    assert selected.sha256 == m._sha(selected.canonical_bytes())
    assert b"PRIVATE FINANCIAL SENTINEL" not in selected.canonical_bytes()


def test_request_preserves_raw_cik_source_ordinal_exact_master_folder_and_hashes(corpus):
    body = _finish(_pipeline(corpus)).to_payload()
    for ordinal, row in enumerate(body["requests"], 1):
        source, request = row["source"], row["request"]
        assert row["selection_ordinal"] == ordinal and set(request) == m._REQUEST_KEYS
        assert request["issuer_cik"] == source["raw_issuer_cik"]
        assert request["source_record_ordinal"] == source["source_record_ordinal"]
        assert request["filing_metadata_sha256"] == row["source_record_sha256"] == source["filing_metadata_sha256"]
        assert request["archive_path"].startswith("edgar/data/999/")
        assert row["request_sha256"] == m._sha(m._raw(request))
        assert row["pre_normalization_target"]["complete_submission_url"] == request["url"]
    first = body["requests"][0]
    assert first["request"]["issuer_cik"] == "123" and first["source"]["issuer_comparison_key"] == "0000000123"


@pytest.mark.parametrize("state", sorted(m.audit._STATES))
def test_all_prior_consumption_states_are_suppressed_with_no_body_releasing_them(corpus, state):
    targets = _pilot_targets(corpus)
    body = _finish(_pipeline(corpus, consumed=[(targets[0], state)])).to_payload()
    assert body["requests"][0]["request"]["accession_number"] == targets[1]["accession_number"]
    assert targets[0]["accession_number"] not in {row["request"]["accession_number"] for row in body["requests"]}
    assert body["selection_period_observed_fresh_count"] == 71
    assert body["global_consumed_accessions"] == 1
    assert body["separate_diagnostic_does_not_resolve_original_ambiguous_start"] is True


def test_later_cross_quarter_repeat_removes_first_candidate_and_refills_prefix(corpus):
    helper, supplied, _, _ = corpus;targets = _pilot_targets(corpus)
    changed = helper._changed(supplied, "2021Q2", lambda raw: helper._fields(raw, 3, "ACCESSION_NUMBER", targets[0]["accession_number"]))
    body = _finish(_pipeline(corpus, supplied=changed)).to_payload()
    assert body["requests"][0]["request"]["accession_number"] == targets[1]["accession_number"]
    assert body["requests"][-1]["request"]["accession_number"] == targets[64]["accession_number"]
    assert body["selection_period_observed_fresh_count"] == 72
    assert body["selection_period_suppressed_late_repeat_count"] == body["global_repeat_accessions_observed"] == 1
    assert body["selection_period_eligible_after_global_suppression_count"] == 71


def test_locator_quarantine_does_not_get_an_issuer_fabricated_url(corpus):
    targets = _pilot_targets(corpus)
    body = _finish(_pipeline(corpus, omit=[targets[0]["accession_number"]])).to_payload()
    assert body["requests"][0]["request"]["accession_number"] == targets[1]["accession_number"]
    assert body["parent_pilot_counts"]["locator_quarantined_targets"] == 1


def test_underfilled_exact_period_refuses_instead_of_borrowing_another_quarter(corpus):
    pipeline = _pipeline(corpus, consumed=[(row, "reserved") for row in _pilot_targets(corpus)[:9]])
    with pytest.raises(m.PilotSecFreshSelectionError, match="prefix_underfilled"): _finish(pipeline)
    with pytest.raises(m.PilotSecFreshSelectionError, match="not_active"): _finish(pipeline)


@pytest.mark.parametrize("fault", ["roster_pin", "audit_pin", "fake_roster", "fake_audit", "replaced_roster", "replaced_audit"])
def test_factory_finish_requires_genuine_full_roster_audit_and_external_pins(corpus, fault):
    pipeline = _pipeline(corpus);changes = {}
    if fault == "roster_pin": changes["expected_roster_sha256"] = "f" * 64
    if fault == "audit_pin": changes["expected_audit_sha256"] = "f" * 64
    if fault == "fake_roster": changes["roster"] = SimpleNamespace(to_payload=pipeline[1].to_payload, sha256=pipeline[1].sha256)
    if fault == "fake_audit": changes["audit"] = SimpleNamespace(to_payload=pipeline[2].to_payload, sha256=pipeline[2].sha256)
    if fault == "replaced_roster": changes["roster"] = replace(pipeline[1])
    if fault == "replaced_audit": changes["audit"] = replace(pipeline[2])
    with pytest.raises((m.PilotSecFreshSelectionError, ValueError)): _finish(pipeline, **changes)
    with pytest.raises(m.PilotSecFreshSelectionError, match="not_active"): _finish(pipeline)


def test_unchanged_source_hash_does_not_cover_changed_nonselected_disposition(corpus):
    def mutate(row):
        if row["source"]["period"] == "2026Q1": row["disposition"] = "invented-different-context-disposition"
    pipeline = _pipeline(corpus, mutate=mutate)
    with pytest.raises(m.PilotSecFreshSelectionError, match="completed_stream_binding"): _finish(pipeline)


def test_prefix_does_not_finish_before_remaining_context_source_callbacks(corpus):
    pipeline = _pipeline(corpus)
    builder = m.PilotSecFreshSelectionBuilder()
    for row in pipeline[3]:
        if row["source"]["period"] <= "2021Q1": builder.consume(row)
    with pytest.raises(m.PilotSecFreshSelectionError, match="complete_25quarter"):
        builder.finish(roster=pipeline[1], audit=pipeline[2], expected_roster_sha256=pipeline[1].sha256,
            expected_audit_sha256=pipeline[2].sha256)


@pytest.mark.parametrize("fault", ["unknown", "authority", "bool", "source_hash", "ordinal"])
def test_callback_refusal_poisoning_is_not_recoverable_by_skipping_bad_row(corpus, fault):
    pipeline = _pipeline(corpus);row = deepcopy(pipeline[3][0]);builder = m.PilotSecFreshSelectionBuilder()
    if fault == "unknown": row["unexpected"] = "PRIVATE"
    if fault == "authority": row["dispatch_authorized"] = True
    if fault == "bool": row["prior_consumed"] = 0
    if fault == "source_hash": row["source_record_sha256"] = "f" * 64
    if fault == "ordinal": row["source"]["source_record_ordinal"] = 2
    with pytest.raises((m.PilotSecFreshSelectionError, ValueError)): builder.consume(row)
    with pytest.raises(m.PilotSecFreshSelectionError, match="not_active"): builder.consume(pipeline[3][0])


def test_completed_factory_is_immutable_and_serialized_validation_is_not_a_seal(corpus):
    pipeline = _pipeline(corpus)
    result = _finish(pipeline);before = result.canonical_bytes()
    body = result.to_payload();body["requests"][0]["request"]["issuer_cik"] = "999"
    assert result.canonical_bytes() == before
    detached = m.validate_selection_payload(result.to_payload())
    assert detached == result.to_payload() and type(detached) is dict
    for fake in (replace(result), m.PilotSecFreshSelection(before, object()), SimpleNamespace(canonical_bytes=lambda: before), detached):
        with pytest.raises(m.PilotSecFreshSelectionError): m.validate_pilot_sec_fresh_selection(fake)
    with pytest.raises(m.PilotSecFreshSelectionError, match="not_active"): _finish(pipeline)
    with pytest.raises(m.PilotSecFreshSelectionError, match="not_active"): pipeline[0].consume(pipeline[3][0])


@pytest.fixture(scope="module")
def selection_body(corpus):
    return _finish(_pipeline(corpus)).to_payload()


@pytest.mark.parametrize("change", [
    lambda value: value.update(unexpected=True), lambda value: value.update(selection_period="2020Q1"),
    lambda value: value.update(selection_limit=63), lambda value: value.update(selected_count=True),
    lambda value: value.update(fixture_only=1), lambda value: value.update(fixture_only=False),
    lambda value: value.update(dispatch_authorized=True),
    lambda value: value.update(backtesting_ready=True), lambda value: value.update(qc_jobs=False),
    lambda value: value.update(new_provider_requests=1), lambda value: value["authority"].update(rights_verified=True),
    lambda value: value["authority"].update(sec_dispatches=0.0),
    lambda value: value.update(all_25_quarters_finished=False),
    lambda value: value.update(source_roster_sha256="bad"),
    lambda value: value.update(selection_period_observed_fresh_count=0),
    lambda value: value["quarter_bindings"].pop(),
    lambda value: value["quarter_bindings"][0]["counts"].update(source_filings=True),
    lambda value: value["source_roster_counts"].update(context_quarters=True),
    lambda value: value["parent_pilot_counts"].update(target_filings=0),
    lambda value: value.update(full_source_row_jsonl_bytes=0),
    lambda value: value.update(selected_metadata_jsonl_sha256="f" * 64),
    lambda value: value["requests"].pop(),
])
def test_serialized_result_rejects_scope_counts_authority_and_roster_laundering(selection_body, change):
    value = deepcopy(selection_body);change(value)
    with pytest.raises((m.PilotSecFreshSelectionError, ValueError)): m.validate_selection_payload(value)


@pytest.mark.parametrize("change", [
    lambda row: row.update(selection_ordinal=2), lambda row: row.update(dispatch_authorized=True),
    lambda row: row.update(source_record_sha256="f" * 64), lambda row: row.update(request_sha256="f" * 64),
    lambda row: row["request"].update(issuer_cik="0000000123"),
    lambda row: row["request"].update(source_record_ordinal=True),
    lambda row: row["request"].update(url="https://www.sec.gov/Archives/edgar/data/123/0000000001-21-100003.txt"),
    lambda row: row["request"].update(private_extra="PRIVATE"),
    lambda row: row["pre_normalization_target"].update(issuer_cik="0000000123"),
    lambda row: row["selected_locator"].update(archive_path="edgar/data/123/0000000001-21-100003.txt"),
    lambda row: row.update(compiler_disposition_sha256="bad"),
])
def test_serialized_prefix_rejects_changed_raw_request_or_source_links_even_reframed(selection_body, change):
    value = deepcopy(selection_body);change(value["requests"][0]);_reframe(value)
    with pytest.raises((m.PilotSecFreshSelectionError, ValueError)): m.validate_selection_payload(value)


def test_serialized_prefix_repeat_and_reordering_do_not_pass_reframed_hashes(selection_body):
    for repeat in (False, True):
        value = deepcopy(selection_body)
        if repeat:
            value["requests"][1] = deepcopy(value["requests"][0]);value["requests"][1]["selection_ordinal"] = 2
        else:
            value["requests"].reverse()
            for index, row in enumerate(value["requests"], 1): row["selection_ordinal"] = index
        _reframe(value)
        with pytest.raises(m.PilotSecFreshSelectionError, match="order_or_repeat"): m.validate_selection_payload(value)


@pytest.mark.parametrize("fault", ["raw_cik", "source_ordinal"])
def test_coherently_rehashed_request_still_cannot_rewrite_raw_source_identity(selection_body, fault):
    value = deepcopy(selection_body);row = value["requests"][0]
    if fault == "raw_cik":
        row["request"]["issuer_cik"] = row["pre_normalization_target"]["issuer_cik"] = "0000000123"
    else:
        row["request"]["source_record_ordinal"] += 1
    row["request_sha256"] = m._sha(m._raw(row["request"]));_reframe(value)
    with pytest.raises(m.PilotSecFreshSelectionError, match="request_source_binding"):
        m.validate_selection_payload(value)
