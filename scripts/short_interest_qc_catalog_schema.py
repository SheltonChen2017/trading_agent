"""Manual, one-additional-read schema recovery; not a QC execution permit."""
from __future__ import annotations
from collections import Counter
from datetime import datetime, timezone
import re
from data.hashing import hash_payload
from scripts import read_short_interest_qc_engine_metadata as legacy

CLAIM = "manual-schema-recovery-request.claim.json"
OLD_CLAIM_SHA256 = "02bf32970fcf71e9ba6b325042a1a75d8956a9923e958d3d3a0b92239e8e9452"
OLD_REFUSAL_SHA256 = "b21c15229beb278e8db0ab6c1a9fa9a22f0a98d773dbe7dc4dacc796bba7e307"
OLD_HEAD = "904cb16d678c31c19617e22c06992fd3aa3ba831"
MAXIMUM_ROWS = 10_000
FIELDS = tuple(sorted(legacy.VERSION_FIELDS))

class RecoveryRefusal(ValueError):
    def __init__(self, code):
        codes = {"protocol_refused", "legacy_custody_refused", "request_budget_consumed", "scope_changed",
            "protected_storage_refused", "named_credentials_unavailable", "credential_echo_discarded",
            "wire_request_refused", "catalog_response_refused", "catalog_scope_refused", "catalog_not_clean", "public_version_unavailable",
            "receipt_clock_refused"}
        self.code = code if code in codes else "protocol_refused"
        super().__init__("REFUSED: " + self.code)

def require(value, code):
    if not value:
        raise RecoveryRefusal(code)

def protocol():
    value = {"schema":"si-manual-qc-catalog-schema-recovery-v2", "method":"POST", "endpoint":legacy.ENDPOINT,
        "body":{}, "maximum_additional_requests":1, "maximum_total_catalog_claims":2,
        "claim":CLAIM, "claim_scope":"same_fixed_protected_parent_never_new_run_or_reset",
        "manual_registered_recovery_only":True, "automatic_retries":0,
        "maximum_response_bytes":legacy.MAX_BYTES, "maximum_rows":MAXIMUM_ROWS,
        "old_claim_sha256":OLD_CLAIM_SHA256, "old_refusal_sha256":OLD_REFUSAL_SHA256, "old_head":OLD_HEAD,
        "known_root_fields":["versions","success","errors"], "known_version_fields":list(FIELDS),
        "errors_omitted":"documented_RestResponse_constructor_default_empty_only",
        "errors_null_nonempty":"not_clean_positive", "nullable_version_fields":"negative_row_not_fabricated",
        "description":"known_optional_nullable_string_omitted_from_public_output_not_engine_identity",
        "public_selection":"complete_explicit_public_true_latest_actual_UTC_created_then_integer_id",
        "diagnostics":"allowlisted_presence_type_counts_ordinals_only_no_unknown_names_values_private_branches_descriptions",
        "private_raw":"protected_after_echo_and_catalog_scope_check_never_public",
        "engine_pin_or_execution_permission":False, "outcome_looks":0, "qc_launch_attempts":0,
        "projects_nodes_history_upload_compile_jobs_backtests":False,
        "primary_sources":["https://www.quantconnect.com/docs/v2/cloud-platform/api-reference/lean-version",
            "https://github.com/QuantConnect/Lean/blob/master/Common/Api/Project.cs",
            "https://github.com/QuantConnect/Lean/blob/master/Common/Api/RestResponse.cs"]}
    value["protocol_sha256"] = hash_payload(value)
    return value

def _type(value):
    return {type(None):"null",bool:"boolean",int:"integer",float:"number",str:"string",list:"array",dict:"object"}.get(type(value),"other")

def scope(value):
    require(type(value) is dict and set(value)<= {"versions","success","errors"}
        and "versions" in value and "success" in value and type(value["versions"]) is list
        and len(value["versions"])<=MAXIMUM_ROWS,"catalog_scope_refused")
    return value

def _created(value):
    require(type(value) is str,"catalog_not_clean")
    match=re.fullmatch(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,7}))?(Z|\+00:00)',value)
    require(match is not None,"catalog_not_clean")
    try:
        at=datetime.fromisoformat(match[1]).replace(tzinfo=timezone.utc)
        require(at.year>1,"catalog_not_clean")
    except ValueError:
        raise RecoveryRefusal("catalog_not_clean") from None
    # Preserve the actual literal in output. Seven DateTime fractional digits
    # are exact comparison ticks, never truncated/binary-float timestamps.
    return at,int((match[2] or "").ljust(7,"0"))

def diagnose_and_select(value):
    scope(value)
    errors=value.get("errors",[])
    clean=value["success"] is True and type(errors) is list and errors==[]
    ids=Counter(row.get("id") for row in value["versions"] if type(row) is dict
                and type(row.get("id")) is int and 0<=row["id"]<=2**31-1)
    diagnostics=[]; public=[]
    for ordinal,row in enumerate(value["versions"]):
        known={field:{"present":type(row) is dict and field in row,
            "type":_type(row[field]) if type(row) is dict and field in row else "absent"} for field in FIELDS}
        reasons=[]
        if type(row) is not dict:
            reasons.append("row_not_object")
        else:
            if set(row)-legacy.VERSION_FIELDS:
                reasons.append("unknown_field_count_nonzero")
            if not set(legacy.PUBLIC_FIELDS)<=set(row):
                reasons.append("incomplete_known_field_presence")
            if row.get("public") is not True:
                reasons.append("not_explicit_public_true")
            if type(row.get("id")) is not int or not 0<=row["id"]<=2**31-1:
                reasons.append("id_not_nonnegative_CSharp_integer")
            elif ids[row["id"]]!=1:
                reasons.append("duplicate_identifiable_id")
            for field in ("leanHash","leanCloudHash"):
                if not legacy._sha(row.get(field)):
                    reasons.append(field+"_not_40_SHA")
            for field in ("name","ref"):
                if type(row.get(field)) is not str or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/\-]{0,199}',row[field]) is None:
                    reasons.append(field+"_not_safe_public_reference")
            if "description" in row and row["description"] is not None and (type(row["description"]) is not str or len(row["description"])>20_000):
                reasons.append("description_not_complete_string")
            try:
                created=_created(row.get("created"))
            except RecoveryRefusal:
                reasons.append("created_not_actual_UTC_DateTime")
            if not reasons and clean:
                public.append((created,row["id"],{field:row[field] for field in legacy.PUBLIC_FIELDS}))
        diagnostics.append({"ordinal":ordinal,"row_type":_type(row),"known_fields":known,
            "unknown_field_count":len(set(row)-legacy.VERSION_FIELDS) if type(row) is dict else 0,
            "qualified_public_candidate":not reasons and clean,"reasons":reasons})
    observed={"schema":"si-public-qc-catalog-schema-observation-v2", "protocol_sha256":protocol()["protocol_sha256"],
        "known_root_fields":{field:{"present":field in value,"type":_type(value[field]) if field in value else "absent"}
                             for field in ("versions","success","errors")},
        "errors_omitted_default_used":"errors" not in value,"catalog_clean":clean,"row_count":len(diagnostics),
        "qualified_public_count":len(public),"row_diagnostics":diagnostics,
        "selected":max(public,key=lambda item:(item[0],item[1]))[2] if public else None,
        "status":"public_metadata_observed" if public else ("public_version_unavailable" if clean else "catalog_not_clean"),
        "runtime_or_wrapper_proof":False,"execution_pin_or_permission":False,
        "actual_outcome_looks":0,"qc_launch_attempts":0}
    return observed
