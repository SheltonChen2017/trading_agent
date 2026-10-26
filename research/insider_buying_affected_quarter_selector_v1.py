"""Supplied-byte selector for affected retained ownership quarters.

One compressed quarter is supplied at a time. Only SUBMISSION metadata row
fields are semantically interpreted; the existing archive integrity boundary
also checks every table's opaque UTF-8/NUL/CRC/hash integrity, and the pinned
profile checks physical table headers. No financial values, parent bodies,
source rows, CIKs or issuer names are returned. This is not IB1B publication,
IB1C admission, an acquisition plan, or the older 82-quarter promotion route.
"""
from __future__ import annotations

from collections import Counter
import csv
from dataclasses import dataclass, field
import hashlib
import io
import json
import re
import weakref
import zipfile

from data.hashing import hash_payload
from research.insider_buying import sec_zip_corpus_census as census
from research.insider_buying import ib1b_82q_offline_runner as headers
from research.insider_buying.sec_bulk_parsed_snapshot import MAX_FIELD_CHARACTERS, MAX_ROWS_PER_TABLE
from research.insider_buying.sec_corpus_scale_preflight import SecQuarterScaleDescriptor, build_sec_corpus_scale_preflight
from research.insider_buying.sec_edgar_acceptance_snapshot import _upstream_submission_filing_date
from research.insider_buying.sec_ib1b_82q_schema_profile import (
    RETAINED_82Q_SCHEMA_PROFILE_SHA256, build_retained_82q_schema_profile_candidate,
    verify_retained_82q_schema_profile,
)


SCHEMA = "insider-retained-affected-quarter-selector-v1"
PROFILE = "INSETF-IB-AFFECTED-QUARTER-METADATA-SELECTOR-v1"
RETAINED_HEADER_SHA256 = "3736b0327a20040d46ff5a26fd18b4154eebb18cbf4be56706cfe232e9f889c0"
MAX_RESULT_BYTES = 1024 * 1024
MAX_MANIFEST_BYTES = 128 * 1024
MAX_ARCHIVE_BYTES = census.MAX_ARCHIVE_BYTES
MAX_CONTROL_BYTES = 1024 * 1024
FORMS = ("3", "3/A", "4", "4/A", "5", "5/A")
_CIK = re.compile(r"[0-9]{1,10}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_ACCESSION = re.compile(r"[0-9]{10}-[0-9]{2}-[0-9]{6}\Z")
_TOKEN = object()
_REGISTRY = {}
COUNT_KEYS = frozenset({"quarters_scanned", "submission_rows", "form4_or_4a_rows", "short_cik_rows",
    "short_cik_form4_or_4a_rows", "accession_year_mismatch_rows", "accession_year_mismatch_form4_or_4a_rows",
    "short_cik_quarters", "accession_year_mismatch_quarters", "affected_quarters", "overlap_anomaly_quarters"})
EXPECTED_ACTUAL_COUNTS = {"quarters_scanned": 82, "submission_rows": 4_458_409, "form4_or_4a_rows": 4_034_227,
    "short_cik_rows": 146, "short_cik_form4_or_4a_rows": 132, "accession_year_mismatch_rows": 15,
    "accession_year_mismatch_form4_or_4a_rows": 13, "short_cik_quarters": 9,
    "accession_year_mismatch_quarters": 10, "affected_quarters": 19, "overlap_anomaly_quarters": 0}
EXPECTED_ACTUAL_FORM_COUNTS = {"3": 331258, "3/A": 15819, "4": 3934823, "4/A": 99404, "5": 74654, "5/A": 2451}


class AffectedQuarterSelectorError(ValueError):
    """Fixed refusal codes only; source/provider text is never serialized."""


def _need(value, code):
    if not value:raise AffectedQuarterSelectorError(code)


def _raw(body):return json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
def _sha(raw):return hashlib.sha256(raw).hexdigest()
def _periods():return tuple(f"{year}Q{quarter}" for year in range(2006, 2027) for quarter in range(1, 5) if (year,quarter)<=(2026,2))
def _digest(value):
    _need(type(value) is str and _SHA.fullmatch(value) is not None, "external_digest_required")
    return value


def _authority():
    return {**dict.fromkeys(("sec_origin_authenticated", "quarter_population_complete", "complete_parent_admitted",
        "official_acceptance_verified", "publication_time_verified", "point_in_time_verified", "rights_verified",
        "canonical_ready", "direct_ib1c_ingest_authorized", "scale_promotion_authorized", "pilot_ingest_authorized",
        "qc_entitlement_verified", "outcome_access_authorized", "backtesting_ready", "execution_authorized"), False),
        "sec_dispatches": 0, "qc_jobs": 0, "research_looks": 0}


@dataclass(frozen=True, slots=True)
class QuarterArchive:
    period: str
    raw_bytes: bytes = field(repr=False)


def _census_receipt(quarters, manifest_sha, manifest_bytes, fixture_only):
    planning = build_sec_corpus_scale_preflight(SecQuarterScaleDescriptor(period=item.period,
        zip_sha256=item.zip_sha256, zip_size_bytes=item.zip_size_bytes,
        submission_accession_count=item.submission_accessions, form4_accession_count=item.form4_accessions,
        form4a_accession_count=item.form4a_accessions, multi_owner_target_count=None) for item in quarters)
    scope = "synthetic_test_census" if fixture_only else "retained_noncanonical_zip_census"
    return census.SecZipCorpusCensus(scope=scope, source_manifest_sha256=manifest_sha,
        source_manifest_size_bytes=manifest_bytes, quarters=quarters, existing_zip_bytes=planning.existing_zip_bytes,
        submission_accessions=planning.declared_submission_accessions, form4_accessions=planning.declared_form4_accessions,
        form4a_accessions=planning.declared_form4a_accessions, target_accessions=planning.declared_target_accessions,
        multi_owner_unknown_quarters=planning.multi_owner_unknown_quarters,
        planned_distinct_artifacts_without_cache=planning.planned_distinct_artifacts_without_cache,
        maximum_attempts_at_three_per_artifact=planning.maximum_attempts_at_three_per_artifact,
        ideal_minimum_dispatch_span_ms=planning.ideal_minimum_dispatch_span_ms,
        successful_raw_parent_cap_bytes=planning.successful_raw_parent_cap_bytes,
        existing_zip_plus_successful_parent_cap_bytes=planning.existing_zip_plus_successful_parent_cap_bytes,
        acceptance_metadata_records_required_without_cache=planning.declared_target_accessions,
        _validated_quarters_sha256=hash_payload([item.to_payload() for item in quarters]),
        _construction_token=census._SYNTHETIC_CONSTRUCTION_TOKEN if fixture_only else census._RETAINED_CONSTRUCTION_TOKEN)


def _header_receipt(quarters, census_sha, fixture_only):
    return headers.Ib1b82qHeaderPreflight(scope="synthetic_test_header_preflight" if fixture_only else "retained_noncanonical_header_preflight",
        census_sha256=census_sha, schema_profile_sha256=RETAINED_82Q_SCHEMA_PROFILE_SHA256, quarters=quarters,
        compressed_zip_bytes=sum(item.zip_size_bytes for item in quarters),
        expanded_table_bytes=sum(item.expanded_table_bytes for item in quarters),
        _validated_quarters_sha256=hash_payload([item.to_payload() for item in quarters]),
        _construction_token=headers._SYNTHETIC_CONSTRUCTION_TOKEN if fixture_only else headers._RETAINED_CONSTRUCTION_TOKEN)


def _submission_anomalies(raw, quarter):
    form_counts, short_forms, mismatch_forms = Counter(), Counter(), Counter()
    row_count = 0;dialect = None;seen = set()
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            member = archive.getinfo("SUBMISSION.tsv")
            with archive.open(member) as stream:
                reader = csv.reader(io.TextIOWrapper(stream, encoding="utf-8-sig", newline=""), delimiter="\t", strict=True)
                fieldnames = tuple(next(reader))
                _need(fieldnames == quarter.submission_headers, "source_submission_header_changed")
                pos = {name: fieldnames.index(name) for name in ("ACCESSION_NUMBER", "DOCUMENT_TYPE", "FILING_DATE", "ISSUERCIK")}
                for ordinal,values in enumerate(reader, start=1):
                    _need(ordinal <= MAX_ROWS_PER_TABLE and len(values)==len(fieldnames)
                        and all(len(value)<=MAX_FIELD_CHARACTERS for value in values), "source_submission_row_bound_or_width_refused")
                    accession,form,raw_date,raw_cik = (values[pos[key]] for key in pos)
                    _need(_ACCESSION.fullmatch(accession) is not None and accession not in seen, "source_accession_invalid_or_duplicated")
                    seen.add(accession)
                    _need(form in FORMS, "source_ownership_form_refused")
                    _need(_CIK.fullmatch(raw_cik) is not None and int(raw_cik)>0, "source_cik_lexical_shape_refused")
                    filed,current_dialect = _upstream_submission_filing_date(raw_date)
                    _need((filed.year,(filed.month-1)//3+1)==(int(quarter.period[:4]),int(quarter.period[-1])), "source_filing_date_outside_quarter")
                    _need(dialect is None or dialect==current_dialect, "source_filing_date_dialects_mixed")
                    dialect=current_dialect;row_count+=1;form_counts[form]+=1
                    # Preserve raw supplied bytes. Padding is permitted only
                    # for a future comparison key, never by rewriting input.
                    if len(raw_cik)<10:short_forms[form]+=1
                    if int(accession[11:13])!=filed.year%100:mismatch_forms[form]+=1
    except AffectedQuarterSelectorError:raise
    except (ValueError, UnicodeError, csv.Error, OSError, RuntimeError, EOFError, StopIteration, KeyError):
        raise AffectedQuarterSelectorError("source_submission_decode_refused") from None
    _need(row_count==quarter.submission_accessions and tuple(form_counts[form] for form in FORMS)==quarter.form_counts,
        "source_submission_census_partition_differs")
    return {"submission_rows": row_count, "form4_or_4a_rows": form_counts["4"]+form_counts["4/A"],
        "source_form_counts": {form:form_counts[form] for form in FORMS},
        "short_cik_rows": sum(short_forms.values()), "short_cik_form4_or_4a_rows": short_forms["4"]+short_forms["4/A"],
        "short_cik_form_counts": {form:short_forms[form] for form in FORMS},
        "accession_year_mismatch_rows": sum(mismatch_forms.values()),
        "accession_year_mismatch_form4_or_4a_rows": mismatch_forms["4"]+mismatch_forms["4/A"],
        "accession_year_mismatch_form_counts": {form:mismatch_forms[form] for form in FORMS},
        "filing_date_dialect": dialect}


@dataclass(frozen=True, slots=True, weakref_slot=True)
class AffectedQuarterSelection:
    _bytes: bytes = field(repr=False)
    _token: object = field(repr=False, compare=False)

    def canonical_bytes(self):
        registered=_REGISTRY.get(id(self))
        _need(type(self) is AffectedQuarterSelection and self._token is _TOKEN and registered is not None
            and registered[0]() is self and type(self._bytes) is bytes and registered[1]==self._bytes,
            "genuine_unchanged_affected_selection_required")
        return self._bytes

    def to_payload(self):return json.loads(self.canonical_bytes())
    @property
    def sha256(self):return _sha(self.canonical_bytes())


def select_affected_quarters(*, intake_manifest_raw, expected_manifest_sha256, quarter_inputs,
        expected_census_sha256, expected_header_preflight_sha256, fixture_only):
    """Inspect supplied quarter bytes; no filesystem/network/publication API.

    The caller supplies each exact ordered image once through a one-pass
    iterator. Original acquisition clocks are retained only as explicitly
    unverified filesystem observations; this creates no new source clock.
    """
    _need(type(fixture_only) is bool, "explicit_selector_profile_required")
    _need(type(intake_manifest_raw) is bytes and 0<len(intake_manifest_raw)<=MAX_MANIFEST_BYTES
        and _sha(intake_manifest_raw)==_digest(expected_manifest_sha256), "intake_manifest_external_hash_refused")
    _digest(expected_census_sha256);_digest(expected_header_preflight_sha256)
    if not fixture_only:
        _need(expected_manifest_sha256==census.RETAINED_ZIP_MANIFEST_SHA256 and len(intake_manifest_raw)==census.RETAINED_ZIP_MANIFEST_SIZE_BYTES
            and expected_census_sha256==headers.RETAINED_82Q_CENSUS_SHA256
            and expected_header_preflight_sha256==RETAINED_HEADER_SHA256, "fixed_retained_selector_anchors_required")
    try:bindings=census._manifest_bindings(intake_manifest_raw)
    except ValueError:raise AffectedQuarterSelectorError("intake_manifest_exact_inventory_refused") from None
    _need(tuple(binding.period for binding in bindings)==_periods(), "exact_source_period_order_required")
    try:_need(iter(quarter_inputs) is quarter_inputs, "one_pass_quarter_input_required")
    except TypeError:raise AffectedQuarterSelectorError("one_pass_quarter_input_required") from None
    profile=build_retained_82q_schema_profile_candidate();verify_retained_82q_schema_profile(profile)
    quarters,header_quarters,records=[],[],[]
    for binding in bindings:
        try:item=next(quarter_inputs)
        except StopIteration:raise AffectedQuarterSelectorError("complete_82_source_images_required") from None
        _need(type(item) is QuarterArchive and item.period==binding.period and type(item.raw_bytes) is bytes
            and 0<len(item.raw_bytes)<=MAX_ARCHIVE_BYTES and len(item.raw_bytes)==binding.size_bytes
            and _sha(item.raw_bytes)==binding.sha256, "ordered_bound_source_image_required")
        try:
            quarter=census._census_quarter(item.raw_bytes,binding)
            header=headers._quarter_headers(item.raw_bytes,binding.period,profile)
            _need(header.header_line_sha256[0]==quarter.submission_header_line_sha256, "source_header_census_disagrees")
            stats=_submission_anomalies(item.raw_bytes,quarter)
        except AffectedQuarterSelectorError:raise
        except ValueError:raise AffectedQuarterSelectorError("source_archive_or_profile_integrity_refused") from None
        records.append({"period": binding.period, "zip_sha256":binding.sha256, "zip_size_bytes":binding.size_bytes,
            "submission_member_sha256":quarter.submission_member_sha256, "submission_member_bytes":quarter.submission_member_size_bytes,
            "submission_header_line_sha256":quarter.submission_header_line_sha256,
            "schema_header_receipt_sha256":hash_payload(header.to_payload()), "census_quarter_sha256":hash_payload(quarter.to_payload()),
            "local_filesystem_observation_unverified":binding.local_last_write_utc, **stats,
            "selected_affected":stats["short_cik_rows"]>0 or stats["accession_year_mismatch_rows"]>0})
        quarters.append(quarter);header_quarters.append(header)
        del item
    sentinel=object();_need(next(quarter_inputs,sentinel) is sentinel, "extra_source_image_refused")
    recomputed_census=_census_receipt(tuple(quarters),expected_manifest_sha256,len(intake_manifest_raw),fixture_only)
    _need(recomputed_census.sha256==expected_census_sha256, "external_full_census_differs")
    recomputed_headers=_header_receipt(tuple(header_quarters),expected_census_sha256,fixture_only)
    _need(recomputed_headers.sha256==expected_header_preflight_sha256, "external_header_preflight_differs")
    short_periods=[row["period"] for row in records if row["short_cik_rows"]]
    mismatch_periods=[row["period"] for row in records if row["accession_year_mismatch_rows"]]
    affected_periods=[row["period"] for row in records if row["selected_affected"]]
    counts={"quarters_scanned":len(records), **{key:sum(row[key] for row in records) for key in (
        "submission_rows","form4_or_4a_rows","short_cik_rows","short_cik_form4_or_4a_rows",
        "accession_year_mismatch_rows","accession_year_mismatch_form4_or_4a_rows")},
        "short_cik_quarters":len(short_periods),"accession_year_mismatch_quarters":len(mismatch_periods),
        "affected_quarters":len(affected_periods),"overlap_anomaly_quarters":len(set(short_periods)&set(mismatch_periods))}
    forms={form:sum(row["source_form_counts"][form] for row in records) for form in FORMS}
    _need(set(counts)==COUNT_KEYS and all(type(value) is int and value>=0 for value in counts.values())
        and sum(forms.values())==counts["submission_rows"] and forms["4"]+forms["4/A"]==counts["form4_or_4a_rows"],
        "strict_complete_selector_accounting_required")
    if not fixture_only:
        _need(counts==EXPECTED_ACTUAL_COUNTS and forms==EXPECTED_ACTUAL_FORM_COUNTS
            and short_periods==[f"{year}Q{quarter}" for year in range(2020,2023) for quarter in range(1,5)
                if (2020,4)<=(year,quarter)<=(2022,4)] and "2006Q1" in mismatch_periods,
            "recorded_actual_anomaly_profile_differs")
    body={"schema":SCHEMA,"profile":PROFILE,"fixture_only":fixture_only,"source_window":"2006Q1..2026Q2",
        "intake_manifest_sha256":expected_manifest_sha256,"intake_manifest_bytes":len(intake_manifest_raw),
        "retained_source_capture_commit":census._CAPTURE_COMMIT,"census_sha256":expected_census_sha256,
        "header_preflight_sha256":expected_header_preflight_sha256,"schema_profile_sha256":RETAINED_82Q_SCHEMA_PROFILE_SHA256,
        "quarters":records,"quarters_sha256":_sha(_raw(records)),"short_cik_periods":short_periods,
        "accession_year_mismatch_periods":mismatch_periods,"affected_periods":affected_periods,
        "counts":counts,"source_form_counts":forms,
        "selection_rule":"source_short_raw_ascii_cik_or_accession_year_different_from_source_filing_year_across_all_six_forms",
        "count_semantics":"sums_of_within_quarter_unique_source_accessions_not_cross_quarter_global_deduplication",
        "raw_source_cik_rewritten":False,"comparison_padding_does_not_change_original_bytes":True,
        "source_observation_clock_kind":"unverified_original_local_filesystem_last_write_not_retrieval_acceptance_publication_or_pit",
        "source_rows_or_ciks_or_names_published":False,"financial_values_interpreted_or_projected":False,
        "other_table_rows_parsed":False,"existing_table_integrity_utf8_crc_hash_checks_performed":True,
        "ib1b_snapshots_published":False,"complete_parent_inputs":0,"whole_population_promotion_sha256":None,
        "authority":_authority()}
    encoded=_raw(body);_need(len(encoded)<=MAX_RESULT_BYTES,"selector_output_bound_refused")
    result=AffectedQuarterSelection(encoded,_TOKEN)
    _REGISTRY[id(result)]=(weakref.ref(result,lambda _,key=id(result):_REGISTRY.pop(key,None)),encoded)
    result.canonical_bytes();return result


def validate_affected_selection_payload(payload, **source_arguments):
    """Full known-input readback; caller supplies a fresh ordered byte stream.

    This re-executes the selection and complete source/header census. A caller
    cannot substitute equal-count quarters or self-rehashed metadata. Actual
    file custody/source authenticity remain the isolated caller's duty.
    """
    _need(type(payload) is dict,"strict_selector_readback_payload_required")
    repeated=select_affected_quarters(**source_arguments)
    _need(_raw(payload)==repeated.canonical_bytes(),"input_derived_selector_payload_differs")
    return {"schema":SCHEMA,"profile":PROFILE,"sha256":repeated.sha256,
        "counts":repeated.to_payload()["counts"],"authority":_authority()}
