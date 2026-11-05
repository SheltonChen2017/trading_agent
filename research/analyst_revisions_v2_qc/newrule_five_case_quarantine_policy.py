"""Exact original five-case denial policy; stdlib-only, no source/launch authority.

A supplied five-row catalog binds original content by fixed whole-row hashes.
It does not authenticate a fresh full source census, resolve identities, or
perform any machine, provider, QC or credential operation.
"""
import hashlib
import json


class NewruleError(ValueError):
    """Finite original-binding/catalog predicate only."""


def require(condition, code):
    if not condition:
        raise NewruleError(code)


def canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError, UnicodeError):
        raise NewruleError("quarantine_catalog") from None


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def require_sha(value):
    require(type(value) is str and len(value) == 64
        and all(char in "0123456789abcdef" for char in value), "digest")
    return value


SCHEMA = "arv2-r337-five-case-quarantine-target-v1"
CATALOG_SCHEMA = "arv2-r337-five-case-quarantine-catalog-v1"
LEDGER_SCHEMA = "arv2-r337-five-case-quarantine-transfer-v1"
RESEARCH_EPOCH_ID = "R337-five-case-quarantine-exploratory-v1"
AR_PERCENTS = (0, 100, 200)
ORIGINAL_BINDING_COUNT = 6151
ORIGINAL_BINDING_STREAM_SHA256 = "73ba4ac73c0485b2d274c31b5ec740a97a64de27a4f6dfbfb9cb63bc8e7cd15f"
ADMISSION_SHA256 = "5d0075cfe24cdfaaa56992de1d3b30bb4895d2495a8356ade47a4c3bc9dea281"
QUARANTINED_WHOLE_BINDING_SHA256S = (
    "f352b4d726b30dc4c0d9ac2b607d4c003dc8ebc4de2fc7442b97b6d8c3f1b986",
    "b0147c90e6741dc9b7697b82cc1d1dc459a0de4445d54c540cdfa7e9319fdce8",
    "c15d10303e03ea8eb0ce007bed1db63bfc626337dcda2bd94798ef09a5c058f7",
    "1e241c9aca6d79eef7020990ffa7bca14b8059a72e67bb42a767690ded624331",
    "b44a76e5db7cedcfc5ddfa6671b6cb28feb306d434d8d3cda3710fb7e3fd61c9",
)
FALSE_FLAGS = {"point_in_time_proven": False, "formal_identity_admitted": False,
    "formal_forward_ready": False, "paper_or_live_ready": False,
    "source_admission_granted": False}


def profile_record():
    return {"schema": SCHEMA, "catalog_schema": CATALOG_SCHEMA,
        "ledger_schema": LEDGER_SCHEMA, "evidence_epoch": RESEARCH_EPOCH_ID,
        "baseline_schema": "arv2-accepted-risk-newrule-target-v1",
        "original_binding_count": ORIGINAL_BINDING_COUNT,
        "original_binding_stream_sha256": ORIGINAL_BINDING_STREAM_SHA256,
        "quarantined_whole_binding_sha256s": list(QUARANTINED_WHOLE_BINDING_SHA256S),
        "universe_counts": [6, 8], "AR_percents": list(AR_PERCENTS),
        "quarantine_timing": "after_all_sleeve_construction_shared_caps_and_final_AR_tilt",
        "destination": "each_denied_final_sleeve_weight_to_that_sleeves_own_ETF",
        "selection": "no_promotion_no_renormalization_no_cash_change_no_unit_substitution",
        "census": "complete_original_6151_and_all_eight_books_preserved",
        "window": "same_frozen_W5_period_no_date_or_membership_clipping",
        "holdings": "runtime_must_refuse_any_denied_held_position_before_price_or_order",
        "identity": "exact_original_binding_denial_not_resolved_identity_or_price_admission",
        "catalog_stream_commitment": "original_identity_pin_not_fresh_catalog_authentication_claim",
        **FALSE_FLAGS}


def quarantine_policy_sha256():
    return digest(profile_record())


def make_quarantine_catalog_from_bindings(exact_five_rows):
    """Bind five supplied original rows; this performs no source or full census I/O."""
    require(type(exact_five_rows) in (list, tuple) and len(exact_five_rows) == 5,
        "quarantine_catalog")
    require(all(type(row) is dict and type(row.get('security_id')) is str
        and 0 < len(row['security_id']) <= 1024 for row in exact_five_rows), "quarantine_binding")
    rows = tuple(json.loads(canonical(row)) for row in exact_five_rows)
    require(tuple(digest(row) for row in rows) == QUARANTINED_WHOLE_BINDING_SHA256S
        and len({row['security_id'] for row in rows}) == 5, "quarantine_binding")
    return {"schema": CATALOG_SCHEMA, "evidence_epoch": RESEARCH_EPOCH_ID,
        "original_binding_stream_sha256": ORIGINAL_BINDING_STREAM_SHA256,
        "original_binding_count": ORIGINAL_BINDING_COUNT,
        "quarantine_policy_sha256": quarantine_policy_sha256(),
        "quarantined_bindings": json.loads(canonical(rows)), **FALSE_FLAGS}


def validate_quarantine_catalog(value, *, expected_sha256):
    require_sha(expected_sha256)
    require(type(value) is dict and set(value) == {'schema', 'evidence_epoch',
        'original_binding_stream_sha256', 'original_binding_count',
        'quarantine_policy_sha256', 'quarantined_bindings', *FALSE_FLAGS}, "quarantine_catalog")
    require(digest(value) == expected_sha256, "quarantine_catalog_pin")
    expected = make_quarantine_catalog_from_bindings(value['quarantined_bindings'])
    require(type(value['original_binding_count']) is int
        and all(value[key] is False for key in FALSE_FLAGS) and value == expected,
        "quarantine_catalog")
    return json.loads(canonical(expected))


def denied_security_ids(value, *, expected_sha256):
    catalog = validate_quarantine_catalog(value, expected_sha256=expected_sha256)
    return tuple(row['security_id'] for row in catalog['quarantined_bindings'])
