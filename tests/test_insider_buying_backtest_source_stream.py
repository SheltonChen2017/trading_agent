"""Invented full-population originals only; no SEC, reference or outcome I/O."""
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import weakref
from zoneinfo import ZoneInfo

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.insider_buying import backtest_source_stream as module
from research.insider_buying.sec_bulk_parsed_snapshot import (
    LoadedSecBulkParsedSnapshot, ParsedSecBulkAccession, ParsedSecBulkRow, _source_row_id,
)
from research.insider_buying.sec_complete_submission import project_sec_complete_submission, SecCompleteSubmissionTarget
from research.insider_buying.sec_ib1c_identity_v2 import assess_ib1c_v2_quarter_identity
from research.insider_buying.sec_ib1c_v2_downstream import build_v2_quarter_coverage, compose_v2_scope_coverage
from test_insider_buying_backtest_evidence_pipeline import make_pipeline_fixture
from test_insider_buying_sec_master_locator_reconciliation import _snapshot, _census
from test_insider_buying_sec_ib1c_v2_downstream import _binding


def _bytes(value):
    return canonical_json(value).encode("utf-8")


_TEMPLATE = None


def _template():
    global _TEMPLATE
    if _TEMPLATE is None:
        source = make_pipeline_fixture({"stocks": 1, "members": 1})
        _TEMPLATE = source["parent_images"][0], json.loads(source["source_manifest"])["parents"][0]["target"]
    return _TEMPLATE


def _source_snapshot(period, specs):
    base = _snapshot(period)
    rows, summaries = [], []
    for offset, (form, filed, issuer, accession, _) in enumerate(specs):
        values = (accession, filed, filed, form, issuer, "Invented", "T00")
        row_id = _source_row_id(
            raw_snapshot_id=base.identity.raw_snapshot_id, raw_lineage_hash=base.identity.raw_lineage_hash,
            raw_archive_sha256=base.identity.raw_archive_sha256, table_name="SUBMISSION.tsv",
            raw_member_sha256="b" * 64, source_record_ordinal=offset + 1, values=values, source_row_key=())
        rows.append(ParsedSecBulkRow("SUBMISSION.tsv", "submission", offset + 1, accession, values, (), row_id))
        summaries.append(ParsedSecBulkAccession(accession, form, row_id, (("SUBMISSION.tsv", (row_id,)),)))
    table = replace(base.identity.tables[0], row_count=len(rows), row_ids_hash=hash_payload([row.row_id for row in rows]))
    identity = replace(base.identity, tables=(table, *base.identity.tables[1:]), lineage_hash="", snapshot_id="")
    lineage = hash_payload(identity.lineage_payload())
    identity = replace(identity, lineage_hash=lineage, snapshot_id=f"sec-insider-parsed-{period.lower()}-{lineage[:16]}")
    census = replace(next(q for q in _census().quarters if q.period == period),
                     form_counts=tuple(sum(s[0] == form for s in specs) for form in module._FORMS))
    return LoadedSecBulkParsedSnapshot(identity, tuple(rows), tuple(summaries)), census


def _record(period, spec, *, title="Common Stock", raw_change=None):
    form, filed, issuer, accession, acceptance = spec
    template, original_target = _template()
    target = SecCompleteSubmissionTarget(**{**original_target, "period": period,
        "accession_number": accession, "form_type": form, "filing_date": filed, "issuer_cik": issuer.zfill(10),
        "complete_submission_url": "https://www.sec.gov/Archives/edgar/data/888888/" + accession + ".txt"})
    raw = (template.replace(b"0000123456-23-000001", accession.encode())
        .replace(b"20230115101112", acceptance.encode())
        .replace(b"20230115", filed.replace("-", "").encode())
        .replace(b"2023-01-13", filed.encode())
        .replace(b"<CIK>0000123456", b"<CIK>" + issuer.zfill(10).encode())
        .replace(b"<issuerCik>0000123456", b"<issuerCik>" + issuer.zfill(10).encode())
        .replace(b"<TYPE>4\n", f"<TYPE>{form}\n".encode())
        .replace(b"<documentType>4</documentType>", f"<documentType>{form}</documentType>".encode())
        .replace(b"Common Stock", title.encode()))
    if raw_change is not None:
        raw = raw_change(raw)
    parent = project_sec_complete_submission(target, raw)
    official = datetime.strptime(parent.accepted_at_raw, "%Y%m%d%H%M%S").replace(
        tzinfo=ZoneInfo("America/New_York")).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    entry = {"target": target.to_payload(), "projection_sha256": parent.sha256,
        "parent_sha256": hash_bytes(raw), "header_sha256": hash_bytes(parent.header_bytes),
        "xml_sha256": hash_bytes(parent.xml_bytes), "official_acceptance_utc": official}
    return module.StreamParentRecord(_bytes(entry), raw)


def _specs(period="2023Q1", count=3, *, forms=None, filed=None, prefix=123456):
    day = filed or ("2023-01-15" if period == "2023Q1" else "2022-12-15")
    return tuple((forms.get(index, "4") if forms else "4", day, "123456",
                  f"{prefix:010d}-{int(period[:4]) % 100:02d}-{index + 1:06d}", day.replace("-", "") + "101112")
                 for index in range(count))


def make_stream_fixture(*, periods=("2023Q1",), count=3, specs_by_period=None, corroborate=False,
                        lookback="2023-01-03", decision="2023-02-24", title="Common Stock"):
    declarations, coverages, specifications = [], [], []
    for period in periods:
        specs = _specs(period, count) if specs_by_period is None else specs_by_period[period]
        snapshot, census = _source_snapshot(period, specs)
        relevant = [(period, spec) for spec in specs if spec[0] in {"4", "4/A"}]
        supplied = tuple(project_sec_complete_submission(
            SecCompleteSubmissionTarget(**json.loads(record.entry_bytes)["target"]), record.raw_bytes)
            for record in (_record(*item, title=title) for item in relevant)) if corroborate else ()
        assessment = assess_ib1c_v2_quarter_identity(snapshot, census, supplied)
        coverage = build_v2_quarter_coverage(assessment, _binding(snapshot, assessment))
        coverages.append(coverage)
        digest = hashlib.sha256()
        for item in relevant:
            digest.update(_record(*item, title=title).entry_bytes + b"\n")
        declarations.append({"period": period, "coverage_sha256": coverage.sha256,
            "parent_count": len(relevant), "ordered_parent_inventory_sha256": digest.hexdigest()})
        specifications.extend(relevant)
    coverages = tuple(coverages)
    scope = compose_v2_scope_coverage(coverages, periods)
    population = _bytes({"schema": "insider-backtest-source-population-v2", "trust_scope": "fixture",
        "origin": "invented-complete-submission", "scope_sha256": scope.sha256,
        "expected_periods": list(periods), "quarters": declarations})
    return {"coverages": coverages, "expected_periods": periods,
        "parent_records": (_record(*item, title=title) for item in specifications),
        "population_manifest": population, "population_sha256": hash_bytes(population), "trust_scope": "fixture",
        "lookback_start_session": lookback, "decision_session": decision,
        "decision_cutoff_utc": decision + "T21:00:00Z"}, specifications


def _edit_manifest(kwargs, edit):
    result = dict(kwargs)
    payload = json.loads(kwargs["population_manifest"])
    edit(payload)
    result["population_manifest"] = _bytes(payload)
    result["population_sha256"] = hash_bytes(result["population_manifest"])
    return result


def test_fullquarter_300_missing_v2_parents_are_genuinely_corroborated_without_old_cap_changes():
    kwargs, _ = make_stream_fixture(count=300)
    preceding = kwargs["coverages"][0].to_payload()
    assert preceding["corroborated_count"] == 0 and preceding["quarantined_count"] == 300
    result = module.build_stream_source_evidence(**kwargs)
    body = result.to_payload()
    assert body["relevant_form4_count"] == body["stream_corroborated_form4_count"] == 300
    assert body["preceding_quarantined_count"] == 300 and body["preceding_corroborated_count"] == 0
    assert body["as_of_transaction_count"] == len(result.transaction_rows()) == 300
    assert body["raw_parent_images_retained"] == 0 and body["eligible_events_evaluated"] is False
    assert body["candidate_signal_count"] is None and body["source_authenticated"] is False
    assert body["qc_jobs"] == body["research_looks"] == body["sec_dispatches"] == 0
    assert result.transaction_rows()[0]["purchase_value_usd"] == "50000"
    assert result.transaction_rows()[0]["provisional_eligible_for_lot_aggregation"] is True
    assert kwargs["coverages"][0].to_payload() == preceding


def test_each_raw_record_is_released_before_requesting_the_next_one():
    kwargs, specs = make_stream_fixture(count=270)
    class ReleaseCheckingIterator:
        def __init__(self):
            self.index, self.previous = 0, None
        def __iter__(self):
            return self
        def __next__(self):
            assert self.previous is None or self.previous() is None, "engine retained an old raw record"
            if self.index == len(specs):
                raise StopIteration
            record = _record(*specs[self.index])
            self.index += 1
            self.previous = weakref.ref(record)
            return record
    stream = ReleaseCheckingIterator()
    result = module.build_stream_source_evidence(**{**kwargs, "parent_records": stream})
    assert len(result.parent_facts()) == 270 and stream.previous() is None


def test_crossquarter_source_scope_binds_all_30_session_window_quarters():
    kwargs, _ = make_stream_fixture(periods=("2022Q4", "2023Q1"), count=2,
                                   lookback="2022-12-15", decision="2023-01-20")
    result = module.build_stream_source_evidence(**kwargs)
    body = result.to_payload()
    assert body["source_start"] == "2022-10-01" and body["source_end"] == "2023-03-31"
    assert body["source_submission_count"] == body["as_of_parent_count"] == 4
    assert len(body["preceding_quarter_bindings"]) == 2
    assert [row["period"] for row in result.transaction_rows()] == ["2022Q4", "2022Q4", "2023Q1", "2023Q1"]


def test_all_six_rows_accounted_and_amendment_eligibility_is_not_fabricated_zero():
    kwargs, _ = make_stream_fixture(count=6, specs_by_period={"2023Q1": _specs(count=6, forms=dict(enumerate(module._FORMS)))})
    result = module.build_stream_source_evidence(**kwargs)
    body = result.to_payload()
    assert body["source_submission_count"] == 6 and body["relevant_form4_count"] == 2
    assert body["source_form_counts"] == dict.fromkeys(module._FORMS, 1)
    assert body["unsupported_form_count"] == 4 and body["whole_six_form_identity_sha256"] is None
    assert body["as_of_amendment_eligibility_not_evaluated_count"] == 1
    amendment = result.parent_facts()[1]
    assert amendment["form_type"] == "4/A" and amendment["transaction_count"] is None
    assert amendment["transaction_accounting_evaluated"] is False and amendment["amends_accession"] is None
    assert len(result.transaction_rows()) == 1


def test_future_amendment_never_excludes_known_original_issuer_or_appears_as_of():
    specs = list(_specs(count=2))
    specs[1] = ("4/A", "2023-03-01", "123456", specs[1][3], "20230301101112")
    kwargs, _ = make_stream_fixture(specs_by_period={"2023Q1": tuple(specs)})
    result = module.build_stream_source_evidence(**kwargs)
    body = result.to_payload()
    assert body["as_of_amended_issuers"] == []
    assert body["stream_corroborated_form4_count"] == 2 and body["future_parent_count"] == 1
    assert body["as_of_parent_count"] == body["as_of_transaction_count"] == 1
    assert body["as_of_amended_issuers"] == [] and body["as_of_issuer_ciks"] == ["0000123456"]
    assert body["future_transaction_count"] is None and body["future_amendment_eligibility_not_evaluated_count"] == 1
    assert all(row["form_type"] == "4" for row in result.parent_facts())


def test_future_original_content_bound_but_does_not_change_asof_transaction_facts():
    specs = list(_specs(count=2))
    specs[1] = ("4", "2023-03-01", "999999", specs[1][3], "20230301101112")
    kwargs, _ = make_stream_fixture(specs_by_period={"2023Q1": tuple(specs)})
    result = module.build_stream_source_evidence(**kwargs)
    assert result.to_payload()["future_original_transaction_count"] == 1
    assert result.to_payload()["as_of_issuer_ciks"] == ["0000123456"]
    assert len(result.transaction_rows()) == 1


def test_preceding_corroborated_small_population_is_compatible_and_never_relabels_old_inputs():
    kwargs, _ = make_stream_fixture(corroborate=True)
    result = module.build_stream_source_evidence(**kwargs)
    assert result.to_payload()["preceding_corroborated_count"] == 3
    assert result.to_payload()["stream_corroborated_form4_count"] == 3


def test_source_only_parser_title_refusals_are_exposed_for_new_external_mapping_not_overridden():
    kwargs, _ = make_stream_fixture(title="Ordinary Shares")
    rows = module.build_stream_source_evidence(**kwargs).transaction_rows()
    assert rows[0]["security_title_raw"] == "Ordinary Shares"
    assert rows[0]["provisional_eligible_for_lot_aggregation"] is False
    assert "exclude_non_common_stock" in rows[0]["provisional_outcomes"]


@pytest.mark.parametrize("edit", [
    lambda body: body.update(schema="wrong"), lambda body: body.update(trust_scope="production"),
    lambda body: body.update(origin="sec-original-complete-submission"),
    lambda body: body.update(scope_sha256="f" * 64), lambda body: body.update(ready=True),
    lambda body: body.update(expected_periods=[]), lambda body: body.update(quarters=[]),
    lambda body: body["quarters"][0].update(period="2023Q2"),
    lambda body: body["quarters"][0].update(coverage_sha256="f" * 64),
    lambda body: body["quarters"][0].update(parent_count=True),
    lambda body: body["quarters"][0].update(parent_count=2),
    lambda body: body["quarters"][0].update(ordered_parent_inventory_sha256="f" * 64),
])
def test_population_guard_refuses_incomplete_changed_or_unbound_inventory(edit):
    kwargs, _ = make_stream_fixture()
    with pytest.raises(module.StreamSourceError):
        module.build_stream_source_evidence(**_edit_manifest(kwargs, edit))


@pytest.mark.parametrize("name,value", [
    ("population_sha256", "a" * 64), ("trust_scope", "PRODUCTION"),
    ("lookback_start_session", "2022-12-15"), ("decision_session", "2023-04-03"),
    ("decision_cutoff_utc", "2023-02-23T21:00:00Z"),
    ("decision_cutoff_utc", "2023-02-24T21:00:00.001Z"),
    ("decision_cutoff_utc", "2023-02-24T21:00:00"),
    ("lookback_start_session", "2023-02-30"), ("decision_session", "2027-09-01"),
    ("lookback_start_session", "2005-12-30"), ("expected_periods", ["2023Q1"]),
])
def test_exact_scope_dates_cutoff_and_external_root_guards(name, value):
    kwargs, _ = make_stream_fixture()
    with pytest.raises(module.StreamSourceError):
        module.build_stream_source_evidence(**{**kwargs, name: value})


def test_missing_quarter_refuses_instead_of_structural_zero():
    kwargs, _ = make_stream_fixture(periods=("2022Q4", "2023Q1"), lookback="2022-12-15", decision="2023-01-20")
    with pytest.raises(module.StreamSourceError, match="missing"):
        module.build_stream_source_evidence(**{**kwargs, "coverages": kwargs["coverages"][:1]})


@pytest.mark.parametrize("mode", ["missing", "extra", "reordered", "duplicate", "list", "not_record", "raw_changed"])
def test_original_stream_cannot_drop_add_reorder_duplicate_or_replace_records(mode):
    kwargs, specs = make_stream_fixture()
    records = [_record(*item) for item in specs]
    if mode == "missing":
        records = records[:-1]
    elif mode == "extra":
        records.append(records[0])
    elif mode == "reordered":
        records.reverse()
    elif mode == "duplicate":
        records[1] = records[0]
    elif mode == "not_record":
        records[0] = records[0].raw_bytes
    elif mode == "raw_changed":
        records[0] = module.StreamParentRecord(records[0].entry_bytes, records[0].raw_bytes.replace(b"500", b"600"))
    with pytest.raises(module.StreamSourceError):
        module.build_stream_source_evidence(**{**kwargs, "parent_records": records if mode == "list" else iter(records)})


@pytest.mark.parametrize("edit", [
    lambda entry: entry.update(official_acceptance_utc="2023-01-15T15:11:13Z"),
    lambda entry: entry.update(parent_sha256="f" * 64), lambda entry: entry.update(header_sha256="f" * 64),
    lambda entry: entry.update(xml_sha256="f" * 64), lambda entry: entry.update(projection_sha256="f" * 64),
    lambda entry: entry.update(official_acceptance_utc="2023-01-15"),
    lambda entry: entry.update(amends_accession="0000123456-23-000000"),
    lambda entry: entry["target"].update(issuer_cik="0000999999"),
    lambda entry: entry["target"].update(quarterly_index_sha256="f" * 64),
])
def test_individually_malformed_parent_entries_refuse_even_before_inventory_digest(edit):
    kwargs, specs = make_stream_fixture()
    records = [_record(*item) for item in specs]
    entry = json.loads(records[0].entry_bytes)
    edit(entry)
    records[0] = module.StreamParentRecord(_bytes(entry), records[0].raw_bytes)
    with pytest.raises(module.StreamSourceError):
        module.build_stream_source_evidence(**{**kwargs, "parent_records": iter(records)})


@pytest.mark.parametrize("name,bound", [("MAX_TOTAL_PARENT_BYTES", 1), ("MAX_COMPACT_BYTES", 1),
    ("MAX_TRANSACTIONS", 1), ("MAX_PARENT_TRANSACTIONS", 0), ("MAX_POPULATION_MANIFEST_BYTES", 1), ("MAX_ENTRY_BYTES", 1)])
def test_finite_resource_bounds_refuse_never_truncate_to_a_ready_scope(monkeypatch, name, bound):
    kwargs, specs = make_stream_fixture()
    records = [_record(*item) for item in specs]
    monkeypatch.setattr(module, name, bound)
    with pytest.raises(module.StreamSourceError):
        module.build_stream_source_evidence(**{**kwargs, "parent_records": iter(records)})


def test_factory_registration_detachment_and_reseal_guards():
    kwargs, _ = make_stream_fixture()
    result = module.build_stream_source_evidence(**kwargs)
    body = result.to_payload(); body["backtest_authorized"] = True
    facts = result.parent_facts(); facts[0]["issuer_cik"] = "0000999999"
    rows = result.transaction_rows(); rows[0]["purchase_value_usd"] = "99999999"
    assert result.to_payload()["backtest_authorized"] is False
    assert result.parent_facts()[0]["issuer_cik"] == "0000123456"
    assert result.transaction_rows()[0]["purchase_value_usd"] == "50000"
    with pytest.raises(module.StreamSourceError):
        replace(result).to_payload()
    with pytest.raises(module.StreamSourceError):
        module.validate_stream_source_evidence(result.to_payload())
    raw = _bytes({"summary": {"ready": True}, "parent_facts": [], "transaction_rows": []})
    object.__setattr__(result, "_bytes", raw)
    object.__setattr__(result, "_factory_bytes", raw)
    with pytest.raises(module.StreamSourceError):
        result.to_payload()


def test_single_parent_compact_expansion_is_bounded_before_storing_transaction_population(monkeypatch):
    kwargs, specs = make_stream_fixture()
    records = [_record(*item) for item in specs]
    monkeypatch.setattr(module, "MAX_PARENT_COMPACT_BYTES", 1, raising=False)
    with pytest.raises(module.StreamSourceError, match="per-parent compact"):
        module.build_stream_source_evidence(**{**kwargs, "parent_records": iter(records)})


def test_genuine_repeated_64k_footnote_cannot_expand_single_parent_past_compact_cap():
    kwargs, specs = make_stream_fixture()
    def expand(raw):
        start = raw.index(b"<nonDerivativeTransaction>")
        end = raw.index(b"</nonDerivativeTransaction>", start) + len(b"</nonDerivativeTransaction>")
        transaction = raw[start:end].replace(
            b"<transactionShares><value>500</value></transactionShares>",
            b'<transactionShares><value>500</value><footnoteId id="f1"/></transactionShares>')
        raw = raw[:start] + transaction * 300 + raw[end:]
        return raw.replace(b"</ownershipDocument>", b'<footnotes><footnote id="f1">'
            + b"Invented explanatory commentary. " * 2200 + b"</footnote></footnotes></ownershipDocument>")
    records = [_record(*specs[0], raw_change=expand), *[_record(*item) for item in specs[1:]]]
    assert len(records[0].raw_bytes) < 2 * 1024 * 1024
    digest = hashlib.sha256()
    for record in records:
        digest.update(record.entry_bytes + b"\n")
    kwargs = _edit_manifest(kwargs, lambda body: body["quarters"][0].update(
        ordered_parent_inventory_sha256=digest.hexdigest()))
    with pytest.raises(module.StreamSourceError, match="per-parent compact transaction expansion"):
        module.build_stream_source_evidence(**{**kwargs, "parent_records": iter(records)})


@pytest.mark.parametrize("period,filed,raw_acceptance", [
    ("2022Q4", "2022-11-06", "20221106013000"),
    ("2023Q1", "2023-03-12", "20230312023000"),
])
def test_source_header_dst_ambiguous_or_nonexistent_timestamp_cannot_enter_stream(period, filed, raw_acceptance):
    spec = (("4", filed, "123456", "0000123456-" + period[2:4] + "-000001", raw_acceptance),)
    kwargs, _ = make_stream_fixture(periods=(period,), specs_by_period={period: spec},
        lookback="2022-11-01" if period == "2022Q4" else "2023-02-01",
        decision="2022-12-01" if period == "2022Q4" else "2023-03-24")
    with pytest.raises(module.StreamSourceError, match="ambiguous or nonexistent"):
        module.build_stream_source_evidence(**kwargs)


def test_factory_registry_releases_source_evidence_when_caller_drops_it():
    kwargs, _ = make_stream_fixture()
    result = module.build_stream_source_evidence(**kwargs)
    key, reference = id(result), weakref.ref(result)
    assert key in module._BUILT
    del result
    assert reference() is None and key not in module._BUILT


@pytest.mark.parametrize("value", [None, True, 5, "{}", bytearray(b"{}")])
def test_population_requires_exact_bytes_and_not_coercion(value):
    kwargs, _ = make_stream_fixture()
    with pytest.raises(module.StreamSourceError):
        module.build_stream_source_evidence(**{**kwargs, "population_manifest": value})


@pytest.mark.parametrize("raw", [b'{"schema":"x","schema":"y"}', b'{"n":NaN}', b'{}\n'])
def test_duplicate_nonfinite_noncanonical_population_json_refuses(raw):
    kwargs, _ = make_stream_fixture()
    with pytest.raises(module.StreamSourceError):
        module.build_stream_source_evidence(**{**kwargs, "population_manifest": raw, "population_sha256": hash_bytes(raw)})
