"""Offline public build-identity qualification, not execution permission.

Some catalog DateTime literals have no timezone. Preserve them as unspecified
wall clocks; never invent UTC or order builds by those clocks. The numerical
public ID is an explicit deterministic software choice, not a recency claim.
"""
from datetime import datetime
import re

from data.hashing import hash_bytes, hash_payload
import scripts.read_short_interest_qc_engine_metadata as legacy
import scripts.short_interest_qc_catalog_schema as schema

REGISTERED_RAW_SHA256 = "69d7ad80fbd3fbb4dfeff4ee03a44e9ba2833e042009006cd03f2f88fe2f409f"


def policy():
    return {"schema": "si-offline-public-qc-build-identity-v1",
        "source_raw_sha256": REGISTERED_RAW_SHA256,
        "selection": "highest_complete_explicit_public_unique_integer_ID_not_created_chronology",
        "created": "exact_valid_DateTime_literal_with_explicit_UTC_or_unspecified_wall_clock_no_timezone_invention",
        "description": "omitted", "provider_requests": 0, "credential_reads": 0,
        "source_processing_permission": False, "runtime_wrapper_proof": False,
        "execution_admitted": False, "actual_outcome_looks": 0, "qc_launch_attempts": 0}


def _clock_basis(value):
    schema.require(type(value) is str, "catalog_not_clean")
    match = re.fullmatch(r"(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})(?:\.(\d{1,7}))?(Z|\+00:00)?", value)
    schema.require(match is not None, "catalog_not_clean")
    try:
        parsed = datetime.fromisoformat(match[1].replace(" ", "T"))
        schema.require(parsed.year > 1, "catalog_not_clean")
    except ValueError:
        raise schema.RecoveryRefusal("catalog_not_clean") from None
    return "explicit_UTC_DateTime_literal" if match[3] else "unspecified_wall_clock_not_a_timestamp"


def qualify_captured_identity(raw):
    schema.require(type(raw) is bytes and hash_bytes(raw) == REGISTERED_RAW_SHA256,
        "legacy_custody_refused")
    value = legacy._parse(raw)
    diagnostic = schema.diagnose_and_select(value)
    candidates, rows = [], []
    for row, observed in zip(value["versions"], diagnostic["row_diagnostics"]):
        reasons = [reason for reason in observed["reasons"] if reason != "created_not_actual_UTC_DateTime"]
        basis = None
        try:
            basis = _clock_basis(row.get("created") if type(row) is dict else None)
        except schema.RecoveryRefusal:
            reasons.append("created_not_valid_source_DateTime_literal")
        qualified = diagnostic["catalog_clean"] and not reasons
        rows.append({"ordinal": observed["ordinal"], "reasons": reasons,
            "created_basis": basis, "qualified_public_identity": qualified})
        if qualified:
            candidates.append(({field: row[field] for field in legacy.PUBLIC_FIELDS}, basis))
    selected = max(candidates, key=lambda pair: pair[0]["id"]) if candidates else None
    return {"schema": "si-captured-public-qc-build-identity-v1", "policy_sha256": hash_payload(policy()),
        "catalog_raw_sha256": REGISTERED_RAW_SHA256, "catalog_clean": diagnostic["catalog_clean"],
        "row_diagnostics": rows, "qualified_public_count": len(candidates),
        "selected": selected[0] if selected else None, "selected_created_basis": selected[1] if selected else None,
        "selection_is_latest_build_claim": False, "execution_admitted": False,
        "runtime_wrapper_proof": False, "source_processing_permission": False,
        "actual_outcome_looks": 0, "qc_launch_attempts": 0}
