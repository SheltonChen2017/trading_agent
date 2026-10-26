"""Pure, private NC-front/source17 joins after a genuine full25-quarter scan.

No file, transport, XML/financial projection or canonical admission occurs.
Source rows are provisional until the unchanged roster factory finishes.
Only routed accessions retain complete raw17 rows; the full population uses
bounded compact occurrence/identity accounting. Later repeats invalidate ALL
matching candidates. Public output is finite counts/dispositions/code pins,
not source/NC values or their hashes. Caller-supplied consumption is not a
named custody attestation. A lexical form/date join is NOT an issuer match.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass,field
import hashlib
import json
import weakref

from research import insider_buying_pilot_sec_roster as roster
from research import insider_buying_pilot_sec_parent_audit as audit
from research import insider_buying_sec_feed_nc_route_v1 as route

SCHEMA="insider-sec-feed-nc-source-binding-v1"
SELF_PATH="research/insider_buying_sec_feed_nc_source_binding_v1.py"
TEST_PATH="tests/test_insider_buying_sec_feed_nc_source_binding_v1.py"
PARENT_SOURCE_PERIODS=("2020Q4",*roster.PILOT_PERIODS)
MAX_SOURCE_ROWS=1500000
MAX_SOURCE_ROW_JSONL_BYTES=MAX_SOURCE_ROWS*audit.MAX_ROW_BYTES
MAX_PRIVATE_SOURCE_BYTES=128*1024**2
MAX_ROUTE_CLAIMS=4096
MAX_PUBLIC_BYTES=2*1024**2
CODE_PINS={"research/insider_buying_pilot_sec_roster.py":"e14c0e23d22604ee583cbb4958ab371ec56b619741a5a2e5da7211db73c7eaf4",
    "research/insider_buying_pilot_sec_parent_audit.py":"eb88a3e9c10f7d4911c313a41b36abe98f476ad4831f657651bf1d19b11f8971",
    route.SELF_PATH:"5d9d24641802c2e826eb8df6f236496a1ba598f29bf2ed8c52852101295a1a59",
    route.TEST_PATH:"0da90d325eeb08b8fb65a86128a66173f5c4ea17c706d466b88bd422b74557b1",
    route.REVIEW_TEST_PATH:"b76815992a26b3f5c4816213a70c8ee21590ad09296692e7d3fc137402e070c0",
    route.PRIVACY_PATH:route.PRIVACY_SHA256}
DISPOSITIONS=frozenset({"source_accession_unmatched","source_cross_quarter_repeat_quarantined",
    "source_cross_quarter_identity_conflict_quarantined","prior_consumed_quarantined",
    "outside_required_parent_source_window","context_non4_form_not_parent_candidate",
    "source_form_or_filing_date_mismatch","private_lexical_source17_candidate_not_admitted"})
_TOKEN=object();_REGISTRY={}


class NCSourceBindingError(ValueError):
    """Static refusal codes only; source/callback exception text stays private."""


def _need(condition,code):
    if not condition:raise NCSourceBindingError(code)


def _raw(value):return json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode("ascii")
def _sha(raw):return hashlib.sha256(raw).hexdigest()


def _authority():
    return {"source_authenticated":False,"complete_original_parent_verified":False,"issuer_or_owner_identity_verified":False,
        "acceptance_or_availability_or_PIT_verified":False,"rights_verified":False,"canonical_admitted":False,
        "backtesting_ready":False,"wrapper_or_collector_or_archive_or_physical_span_verified":False,
        "caller_consumed_set_is_named_custody_attestation":False,"source_metadata_privacy_screened":False,
        "new_code_or_dependency_runtime_bytes_attested_here":False,"files_read_written":0,
        "new_requests":0,"SDK_calls":0,"outcome_looks":0,"XML_or_financial_fields_projected":False}


def _identity(row):
    return _sha(_raw({key:row[key] for key in ("accession_number","form_type","filing_date","issuer_comparison_key")}))


def _classify(claim,rows,consumed):
    if not rows:return "source_accession_unmatched"
    if len(rows)>1:
        return "source_cross_quarter_identity_conflict_quarantined" if len({_identity(row) for row in rows})>1 else "source_cross_quarter_repeat_quarantined"
    row=rows[0]
    if claim.accession_number in consumed:return "prior_consumed_quarantined"
    if row["period"] not in PARENT_SOURCE_PERIODS:return "outside_required_parent_source_window"
    if row["form_type"] not in {"4","4/A"}:return "context_non4_form_not_parent_candidate"
    if claim.form_type!=row["form_type"] or claim.filing_date!=row["filing_date"]:return "source_form_or_filing_date_mismatch"
    return "private_lexical_source17_candidate_not_admitted"


def _batch(value,consumed,fixture):
    _need(type(fixture) is bool,"exact_fixture_boolean_required")
    _need(type(consumed) is frozenset and len(consumed)<=MAX_SOURCE_ROWS
        and all(type(item) is str and audit._ACCESSION.fullmatch(item) for item in consumed),"bounded_consumed_set_required")
    route.validate_nc_route_batch(value)
    witness=route.validate_nc_route_batch_witness(value.public_witness(),fixture_only=fixture)
    _need(value.bound_consumed_accessions()==consumed,"same_caller_consumed_set_required")
    claims=value.eligible_claims();_need(type(claims) is tuple and len(claims)<=MAX_ROUTE_CLAIMS
        and len(claims)==witness["eligible_private_claims"],"bounded_genuine_route_claims_required")
    for index,claim in claims:
        _need(type(index) is int and 0<=index<witness["members"],"route_index_refused")
        route.validate_nc_front_route_claim(claim)
    _need(len({index for index,_ in claims})==len(claims),"duplicate_route_index_refused")
    return witness,claims


def _public(batch_witness,body,stats,records):
    counts=dict(Counter(disposition for _,_,disposition in records))
    return {"schema":SCHEMA,"fixture_only":body["fixture_only"],"route_grammar_profile":route.PROFILE,
        "required_parent_source_window":"2020Q4..2025Q4","entry_pilot_window":"2021Q1..2025Q4",
        "context_source_window":"2020Q1..2026Q1","all25_source_quarters_completed":True,
        "source_population_counts":dict(body["counts"]),"context_form_counts":dict(body["context_form_counts"]),
        "pilot_form_counts":dict(body["pilot_form_counts"]),"source_accounting":dict(stats),
        "route_batch":batch_witness,"eligible_join_disposition_counts":dict(sorted(counts.items())),
        "eligible_join_count":len(records),"route_batch_quarantined_members":batch_witness["members"]-len(records),
        "private_source17_candidate_count":counts.get("private_lexical_source17_candidate_not_admitted",0),
        "all_input_NC_members_accounted":len(records)+(batch_witness["members"]-len(records))==batch_witness["members"],
        "consumption_scope":"exact caller-supplied set; no named journal attestation",
        "source_values_or_value_hashes_exported":False,"code_dependency_pins":dict(CODE_PINS),"authority":_authority()}


@dataclass(frozen=True,slots=True,weakref_slot=True,eq=False)
class NCSourceBinding:
    _batch:object=field(repr=False)
    _roster:object=field(repr=False)
    _consumed:frozenset=field(repr=False)
    _records:tuple=field(repr=False)
    _stats:bytes=field(repr=False)
    _public:bytes=field(repr=False)
    _token:object=field(repr=False,compare=False)

    def public_witness(self):
        validate_nc_source_binding(self);return json.loads(self._public)

    def private_bindings(self):
        """Detached private row metadata plus exact genuine immutable NC claims.

        These contain values and must never be logged/exported as the public
        witness. All dispositions, including nonbindings, remain represented.
        """
        validate_nc_source_binding(self);claims=dict(self._batch.eligible_claims())
        return tuple({"input_index":index,"route_claim":claims[index],"source_rows":tuple(json.loads(raw) for raw in raws),
            "disposition":disposition,"issuer_or_owner_identity_checked":False,"acceptance_evidence_qualified":False,
            "canonical_admitted":False} for index,raws,disposition in self._records)


def validate_nc_source_binding(value):
    _need(type(value) is NCSourceBinding,"exact_NC_source_binding_required")
    saved=_REGISTRY.get(id(value))
    _need(value._token is _TOKEN and type(value._stats) is type(value._public) is bytes
        and type(value._records) is tuple and len(value._records)<=MAX_ROUTE_CLAIMS and saved is not None and saved[0]() is value
        and type(value._consumed) is frozenset
        and all(type(record) is tuple and len(record)==3 and type(record[0]) is int and record[0]>=0
            and type(record[1]) is tuple and type(record[2]) is str for record in value._records)
        and value._batch is saved[1] and value._roster is saved[2]
        and value._consumed==saved[3] and value._records==saved[4] and value._stats==saved[5] and value._public==saved[6],
        "genuine_unchanged_NC_source_binding_required")
    body=roster.validate_pilot_sec_roster(value._roster).to_payload()
    batch_witness,claims=_batch(value._batch,value._consumed,body["fixture_only"])
    _need(tuple(index for index,_,_ in value._records)==tuple(index for index,_ in claims),"binding_route_order_refused")
    for (index,raws,disposition),(_,claim) in zip(value._records,claims,strict=True):
        _need(type(raws) is tuple and len(raws)<=25 and disposition in DISPOSITIONS,"binding_record_refused")
        rows=[]
        for raw in raws:
            _need(type(raw) is bytes and 0<len(raw)<audit.MAX_ROW_BYTES,"private_source_row_bound_refused")
            row,_=audit._source(json.loads(raw));_need(_raw(row)==raw and row["accession_number"]==claim.accession_number,
                "private_source_row_identity_refused");rows.append(row)
        _need(disposition==_classify(claim,rows,value._consumed),"binding_disposition_refused")
    _need(value._public==_raw(_public(batch_witness,body,json.loads(value._stats),value._records)),"binding_public_witness_refused")
    return value


def bind_nc_routes_to_source17(*,route_batch,intake_manifest_raw,expected_manifest_sha256,selection_raw,
        expected_selection_sha256,quarter_inputs,consumed_accessions,fixture_only):
    """Read supplied bytes only; no candidate is returned before genuine finish."""
    batch_witness,claims=_batch(route_batch,consumed_accessions,fixture_only)
    wanted={claim.accession_number for _,claim in claims};matched={key:[] for key in wanted}
    seen={};repeated=set();conflicts=set();row_count=source_bytes=matched_bytes=matched_rows=0
    repeat_occurrences=conflict_occurrences=0;digest=hashlib.sha256();periods=[];ordinal=0;forms=Counter();pilot_forms=Counter();quarter_counts=Counter();failure=[]
    def accept(supplied):
        nonlocal row_count,source_bytes,matched_bytes,matched_rows,repeat_occurrences,conflict_occurrences,ordinal
        _need(row_count<MAX_SOURCE_ROWS,"source_population_row_bound_refused")
        row,line=audit._source(supplied);period=row["period"]
        if not periods or period!=periods[-1]:
            _need(not periods or roster.CONTEXT_PERIODS.index(period)>roster.CONTEXT_PERIODS.index(periods[-1]),"source_quarter_order_refused")
            periods.append(period);ordinal=0
        _need(row["source_record_ordinal"]==ordinal+1,"source_ordinal_gap_or_repeat_refused");ordinal+=1
        _need(source_bytes+len(line)<=MAX_SOURCE_ROW_JSONL_BYTES,"source_population_byte_bound_refused")
        row_count+=1;source_bytes+=len(line);digest.update(line);forms[row["form_type"]]+=1;quarter_counts[period]+=1
        if period in roster.PILOT_PERIODS:pilot_forms[row["form_type"]]+=1
        key=bytes.fromhex(row["accession_key_sha256"]);identity=bytes.fromhex(_identity(row));prior=seen.get(key)
        if prior is None:seen[key]=identity
        else:
            repeated.add(key);repeat_occurrences+=1
            if prior!=identity:conflicts.add(key);conflict_occurrences+=1
        if row["accession_number"] in wanted:
            raw=line[:-1];_need(matched_bytes+len(raw)<=MAX_PRIVATE_SOURCE_BYTES,"private_source_storage_bound_refused")
            bucket=matched[row["accession_number"]];_need(len(bucket)<25,"matching_source_occurrence_bound_refused")
            bucket.append(raw);matched_bytes+=len(raw);matched_rows+=1
        return None
    def consume(supplied):
        try:return accept(supplied)
        except NCSourceBindingError as error:failure.append(error);raise
    try:
        generated=roster.derive_pilot_sec_roster(intake_manifest_raw=intake_manifest_raw,expected_manifest_sha256=expected_manifest_sha256,
            selection_raw=selection_raw,expected_selection_sha256=expected_selection_sha256,quarter_inputs=quarter_inputs,
            consume_row=consume,fixture_only=fixture_only)
    except roster.PilotSecRosterError:
        if failure:raise failure[0] from None
        raise
    except Exception:
        raise NCSourceBindingError("source_derivation_refused") from None
    body=roster.validate_pilot_sec_roster(generated).to_payload()
    _need(tuple(row["period"] for row in body["quarters"])==roster.CONTEXT_PERIODS and body["fixture_only"] is fixture_only
        and body["counts"]["context_quarters"]==25 and body["counts"]["pilot_quarters"]==20
        and all(quarter_counts[row["period"]]==row["submission_rows"] for row in body["quarters"])
        and row_count==body["counts"]["context_submission_rows"] and source_bytes==body["source_row_jsonl_bytes"]
        and digest.hexdigest()==body["source_row_jsonl_sha256"]
        and {form:forms[form] for form in roster.FORMS}==body["context_form_counts"]
        and {form:pilot_forms[form] for form in roster.FORMS}==body["pilot_form_counts"],"complete_source_callback_accounting_refused")
    # Revalidate the exact factory AFTER the potentially long source scan.
    checked,final_claims=_batch(route_batch,consumed_accessions,fixture_only)
    _need(_raw(checked)==_raw(batch_witness) and tuple((i,id(c)) for i,c in claims)==tuple((i,id(c)) for i,c in final_claims),
        "route_batch_changed_during_source_scan")
    records=tuple((index,tuple(matched[claim.accession_number]),_classify(claim,
        [json.loads(raw) for raw in matched[claim.accession_number]],consumed_accessions)) for index,claim in claims)
    stats={"source_rows_accounted":row_count,"source_row_bytes_accounted":source_bytes,"unique_source_accessions":len(seen),
        "cross_quarter_repeat_occurrences":repeat_occurrences,"cross_quarter_repeated_accessions":len(repeated),
        "cross_quarter_identity_conflict_occurrences":conflict_occurrences,"cross_quarter_identity_conflict_accessions":len(conflicts),
        "rows_matching_eligible_route_accessions":matched_rows,"rows_without_eligible_route_accessions":row_count-matched_rows,
        "caller_consumed_accessions":len(consumed_accessions)}
    public=_raw(_public(batch_witness,body,stats,records));_need(len(public)<=MAX_PUBLIC_BYTES,"public_witness_byte_bound_refused")
    result=NCSourceBinding(route_batch,generated,consumed_accessions,records,_raw(stats),public,_TOKEN)
    _REGISTRY[id(result)]=(weakref.ref(result,lambda _,key=id(result):_REGISTRY.pop(key,None)),route_batch,generated,
        consumed_accessions,records,result._stats,public)
    return validate_nc_source_binding(result)
