"""Dangerous-direction tests for the zero-access canonical IB-2 source policy."""
from __future__ import annotations

import ast
import copy
import hashlib
from dataclasses import FrozenInstanceError, fields, replace
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

import research.insider_buying as insider_package
from research.insider_buying import sec_owner_supplied_source_policy as policy_module
from data.hashing import canonical_json, hash_bytes


REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = (
    REPO_ROOT
    / "research"
    / "insider_buying"
    / "sec_owner_supplied_source_policy.py"
)
BLUEPRINT_PATH = (
    REPO_ROOT
    / "docs"
    / "Strategy Description"
    / "INSIDER_BUYING_ETF_STRATEGY_BLUEPRINT.pdf"
)

STRING_FIELDS = (
    "version",
    "schema",
    "directive_id",
    "directive_path",
    "directive_commit",
    "blueprint_path",
    "blueprint_sha256",
    "source_mode",
    "first_period",
    "last_period",
    "partition_field",
    "quarter_coverage_policy",
    "global_acceptance_cutoff_policy",
    "availability_policy",
    "accession_coverage_policy",
    "hash_algorithm",
    "cache_policy",
    "revision_policy",
    "amendment_policy",
)
DATE_FIELDS = (
    "directive_effective_date",
    "first_filing_date",
    "last_filing_date",
)
INTEGER_FIELDS = (
    "expected_period_count",
    "current_external_request_budget",
    "future_internal_requests_per_second_ceiling",
    "authorized_outcome_looks",
    "consumed_outcome_looks",
)
TUPLE_FIELDS = (
    "required_periods",
    "accession_document_types",
    "context_document_types",
    "required_accession_artifacts",
    "hash_bound_objects",
    "amendment_quarantine_reasons",
)
REQUIRED_TRUE_FIELDS = (
    "one_raw_zip_per_quarter_required",
    "form3_and_form5_are_context_only",
    "exact_byte_sizes_required",
    "canonical_ordered_manifest_required",
    "exact_retry_is_idempotent",
    "conflicting_content_refused",
    "retain_every_as_filed_version",
    "future_identifying_contact_required",
    "future_accession_cache_required",
    "future_backoff_and_checkpointing_required",
)
UNBOUND_FIELDS = (
    "global_acceptance_cutoff_utc",
    "source_manifest_id",
    "source_manifest_sha256",
    "official_schema_profile_id",
    "official_schema_profile_sha256",
    "amendment_link_inventory_id",
    "amendment_link_inventory_sha256",
    "title_exception_dictionary_id",
    "title_exception_dictionary_sha256",
    "normalized_role_taxonomy_id",
    "normalized_role_taxonomy_sha256",
    "pit_security_master_id",
    "pit_security_master_sha256",
    "durable_qc_symbol_id_namespace",
    "calendar_session_map_id",
    "calendar_session_map_sha256",
)
REQUIRED_FALSE_FIELDS = (
    "form3_or_form5_canonical_candidate_authorized",
    "simultaneous_original_and_amendment_counting_authorized",
    "future_backtest_network_requests_authorized",
    "real_artifact_read_authorized",
    "source_manifest_bound",
    "official_sec_source_authenticated",
    "official_schema_profile_verified",
    "form4_accession_coverage_verified",
    "amendment_linkage_verified",
    "complete_amendment_coverage_verified",
    "authenticated_supersession_authorized",
    "title_exception_dictionary_verified",
    "normalized_role_taxonomy_verified",
    "official_pit_security_master_verified",
    "durable_qc_symbol_id_verified",
    "trading_calendar_session_mapping_verified",
    "canonical_filtering_authorized",
    "canonical_deduplication_authorized",
    "canonical_aggregation_authorized",
    "canonical_scoring_authorized",
    "canonical_ib2_complete",
    "network_access_authorized",
    "sec_access_authorized",
    "provider_access_authorized",
    "credential_access_authorized",
    "licensed_row_access_authorized",
    "outcome_access_authorized",
    "qc_upload_authorized",
    "qc_processing_authorized",
    "qc_job_authorized",
    "qc_backtest_authorized",
    "broker_access_authorized",
    "operator_database_access_authorized",
    "scheduler_access_authorized",
    "paper_trading_authorized",
    "live_trading_authorized",
    "deployment_authorized",
    "capital_authorized",
    "order_authorized",
    "trading_authority",
)
CONSTANT_BOUND_FIELDS = (
    ("version", "CANONICAL_IB2_SOURCE_POLICY_VERSION"),
    ("schema", "CANONICAL_IB2_SOURCE_POLICY_SCHEMA"),
    ("directive_id", "CANONICAL_IB2_SOURCE_DIRECTIVE_ID"),
    ("directive_path", "CANONICAL_IB2_SOURCE_DIRECTIVE_PATH"),
    ("directive_commit", "CANONICAL_IB2_SOURCE_DIRECTIVE_COMMIT"),
    (
        "directive_effective_date",
        "CANONICAL_IB2_SOURCE_DIRECTIVE_EFFECTIVE_DATE",
    ),
    ("blueprint_path", "CANONICAL_IB2_SOURCE_BLUEPRINT_PATH"),
    ("blueprint_sha256", "CANONICAL_IB2_SOURCE_BLUEPRINT_SHA256"),
    ("source_mode", "CANONICAL_IB2_SOURCE_MODE"),
    ("first_filing_date", "CANONICAL_IB2_SOURCE_FIRST_FILING_DATE"),
    ("last_filing_date", "CANONICAL_IB2_SOURCE_LAST_FILING_DATE"),
    ("partition_field", "CANONICAL_IB2_SOURCE_PARTITION_FIELD"),
    ("quarter_coverage_policy", "CANONICAL_IB2_QUARTER_COVERAGE_POLICY"),
    (
        "global_acceptance_cutoff_policy",
        "CANONICAL_IB2_GLOBAL_ACCEPTANCE_CUTOFF_POLICY",
    ),
    ("availability_policy", "CANONICAL_IB2_AVAILABILITY_POLICY"),
    ("accession_coverage_policy", "CANONICAL_IB2_ACCESSION_COVERAGE_POLICY"),
    ("accession_document_types", "CANONICAL_IB2_ACCESSION_DOCUMENT_TYPES"),
    ("context_document_types", "CANONICAL_IB2_CONTEXT_DOCUMENT_TYPES"),
    (
        "required_accession_artifacts",
        "CANONICAL_IB2_REQUIRED_ACCESSION_ARTIFACTS",
    ),
    ("hash_algorithm", "CANONICAL_IB2_HASH_ALGORITHM"),
    ("hash_bound_objects", "CANONICAL_IB2_HASH_BOUND_OBJECTS"),
    ("cache_policy", "CANONICAL_IB2_CACHE_POLICY"),
    ("revision_policy", "CANONICAL_IB2_REVISION_POLICY"),
    ("amendment_policy", "CANONICAL_IB2_AMENDMENT_POLICY"),
    (
        "amendment_quarantine_reasons",
        "CANONICAL_IB2_AMENDMENT_QUARANTINE_REASONS",
    ),
    ("current_external_request_budget", "CANONICAL_IB2_CURRENT_REQUEST_BUDGET"),
    (
        "future_internal_requests_per_second_ceiling",
        "CANONICAL_IB2_FUTURE_INTERNAL_REQUESTS_PER_SECOND_CEILING",
    ),
)


class _StringSubclass(str):
    pass


class _DateSubclass(date):
    pass


class _IntSubclass(int):
    pass


class _TupleSubclass(tuple):
    pass


class _NoneEqual:
    def __eq__(self, other: object) -> bool:
        return other is None


def _derived_periods() -> tuple[str, ...]:
    return tuple(
        f"{year}Q{quarter}"
        for year in range(2006, 2027)
        for quarter in range(1, 5)
        if (year, quarter) <= (2026, 2)
    )


def _alternate_value(field_name: str) -> object:
    policy = policy_module.CANONICAL_IB2_SOURCE_POLICY
    value = getattr(policy, field_name)
    if field_name in STRING_FIELDS:
        return f"{value}-changed"
    if field_name in DATE_FIELDS:
        return value + timedelta(days=1)
    if field_name in INTEGER_FIELDS:
        return value + 1
    if field_name in TUPLE_FIELDS:
        return (*value, "changed")
    if field_name in REQUIRED_TRUE_FIELDS:
        return False
    if field_name in REQUIRED_FALSE_FIELDS:
        return True
    if field_name in UNBOUND_FIELDS:
        return "bound"
    raise AssertionError(f"uncategorized policy field: {field_name}")


def test_all_policy_fields_are_explicitly_classified() -> None:
    categorized = (
        *STRING_FIELDS,
        *DATE_FIELDS,
        *INTEGER_FIELDS,
        *TUPLE_FIELDS,
        *REQUIRED_TRUE_FIELDS,
        *UNBOUND_FIELDS,
        *REQUIRED_FALSE_FIELDS,
    )
    field_names = tuple(
        field.name
        for field in fields(policy_module.CANONICAL_IB2_SOURCE_POLICY)
    )

    assert len(categorized) == len(set(categorized)) == 99
    assert set(categorized) == set(field_names)


def test_exact_owner_selected_scope_and_governance_evidence() -> None:
    policy = policy_module.CANONICAL_IB2_SOURCE_POLICY

    assert policy.version == "INSETF-IB2-CANONICAL-SOURCE-POLICY-v1"
    assert policy.schema == "insider-buying-canonical-source-policy-v1"
    assert policy.directive_id == "owner-selected-canonical-ib2-source-2026-09-18"
    assert policy.directive_path == (
        "docs/Strategy Description/INSIDER_BUYING_IMPLEMENTATION_RECORD.md"
    )
    assert policy.directive_commit == (
        "2b4c0b9525dd9049d67672daf8abf9961b682029"
    )
    assert policy.directive_effective_date == date(2026, 9, 18)
    assert policy.blueprint_path == (
        "docs/Strategy Description/INSIDER_BUYING_ETF_STRATEGY_BLUEPRINT.pdf"
    )
    assert policy.blueprint_sha256 == (
        "f8834e13bb22d63a1a5a055a24cc2638ecb2e535b733c1fdd1741a28c65db88c"
    )
    assert hashlib.sha256(BLUEPRINT_PATH.read_bytes()).hexdigest() == (
        policy.blueprint_sha256
    )


def test_period_inventory_is_exact_contiguous_and_independently_derived() -> None:
    policy = policy_module.CANONICAL_IB2_SOURCE_POLICY
    expected = _derived_periods()

    assert policy.source_mode == "owner_supplied_immutable_offline_snapshot"
    assert policy.required_periods == expected
    assert policy_module.CANONICAL_IB2_REQUIRED_PERIODS == expected
    assert len(expected) == len(set(expected)) == policy.expected_period_count == 82
    assert (policy.first_period, policy.last_period) == ("2006Q1", "2026Q2")
    assert policy.first_filing_date == date(2006, 1, 1)
    assert policy.last_filing_date == date(2026, 6, 30)
    assert policy.partition_field == "SUBMISSION.FILING_DATE"
    assert policy.quarter_coverage_policy == (
        "exact-contiguous-inclusive-no-missing-duplicate-reordered-or-extra-"
        "periods"
    )


def test_availability_and_accession_evidence_remain_exact_and_offline() -> None:
    policy = policy_module.CANONICAL_IB2_SOURCE_POLICY

    assert policy.global_acceptance_cutoff_utc is None
    assert policy.global_acceptance_cutoff_policy == (
        "none-per-accession-public-availability-only"
    )
    assert policy.availability_policy == (
        "exact-edgar-acceptance-per-accession-never-transaction-bulk-"
        "publication-or-retrieval-time"
    )
    assert policy.one_raw_zip_per_quarter_required is True
    assert policy.accession_document_types == ("4", "4/A")
    assert policy.context_document_types == ("3", "5")
    assert policy.required_accession_artifacts == (
        "acceptance_metadata",
        "complete_primary_ownership_xml",
    )
    assert policy.accession_coverage_policy == (
        "exactly-one-acceptance-metadata-and-one-complete-primary-ownership-"
        "xml-per-bulk-form4-or-form4a-accession-no-missing-extra-duplicate-"
        "conflict-or-cross-accession-match"
    )
    assert policy.form3_and_form5_are_context_only is True
    assert policy.form3_or_form5_canonical_candidate_authorized is False
    assert policy.current_external_request_budget == 0
    assert policy.future_internal_requests_per_second_ceiling == 5
    assert policy.future_identifying_contact_required is True
    assert policy.future_accession_cache_required is True
    assert policy.future_backoff_and_checkpointing_required is True
    assert policy.future_backtest_network_requests_authorized is False


def test_integrity_storage_revision_and_amendment_rules_are_frozen() -> None:
    policy = policy_module.CANONICAL_IB2_SOURCE_POLICY

    assert policy.hash_algorithm == "sha256"
    assert policy.hash_bound_objects == (
        "raw_quarter_zip",
        "raw_zip_member",
        "parsed_quarter_identity",
        "acceptance_metadata_artifact",
        "primary_ownership_xml_artifact",
        "canonical_ordered_period_inventory",
        "canonical_ordered_accession_inventory",
    )
    assert policy.exact_byte_sizes_required is True
    assert policy.canonical_ordered_manifest_required is True
    assert policy.cache_policy == (
        "content-addressed-atomic-immutable-portable-no-overwrite"
    )
    assert policy.exact_retry_is_idempotent is True
    assert policy.conflicting_content_refused is True
    assert policy.revision_policy == "new-evidence-epoch-never-in-place-mutation"
    assert policy.amendment_policy == (
        "retain-every-as-filed-version-no-simultaneous-original-amendment-"
        "count-and-quarantine-unresolved-families"
    )
    assert policy.retain_every_as_filed_version is True
    assert policy.simultaneous_original_and_amendment_counting_authorized is False
    assert policy.amendment_quarantine_reasons == (
        "unresolved",
        "missing_original",
        "ambiguous",
        "branching",
        "cyclic",
        "cross_issuer",
        "temporally_reversed",
    )


def test_every_real_input_is_unbound_and_every_authority_is_false() -> None:
    policy = policy_module.CANONICAL_IB2_SOURCE_POLICY

    for field_name in UNBOUND_FIELDS:
        assert getattr(policy, field_name) is None
    for field_name in REQUIRED_FALSE_FIELDS:
        assert getattr(policy, field_name) is False
    assert policy.authorized_outcome_looks == 0
    assert policy.consumed_outcome_looks == 0


@pytest.mark.parametrize("field_name", STRING_FIELDS)
def test_changed_and_same_valued_string_subclasses_refuse(field_name: str) -> None:
    policy = policy_module.CANONICAL_IB2_SOURCE_POLICY
    with pytest.raises(policy_module.CanonicalIb2SourcePolicyError, match=field_name):
        replace(policy, **{field_name: f"{getattr(policy, field_name)}-changed"})
    with pytest.raises(policy_module.CanonicalIb2SourcePolicyError, match=field_name):
        replace(
            policy,
            **{field_name: _StringSubclass(getattr(policy, field_name))},
        )


@pytest.mark.parametrize("field_name", DATE_FIELDS)
def test_changed_and_same_valued_date_subclasses_refuse(field_name: str) -> None:
    policy = policy_module.CANONICAL_IB2_SOURCE_POLICY
    value = getattr(policy, field_name)
    with pytest.raises(policy_module.CanonicalIb2SourcePolicyError, match=field_name):
        replace(policy, **{field_name: value + timedelta(days=1)})
    with pytest.raises(policy_module.CanonicalIb2SourcePolicyError, match=field_name):
        replace(
            policy,
            **{field_name: _DateSubclass(value.year, value.month, value.day)},
        )
    with pytest.raises(policy_module.CanonicalIb2SourcePolicyError, match=field_name):
        replace(
            policy,
            **{
                field_name: datetime(
                    value.year,
                    value.month,
                    value.day,
                )
            },
        )


@pytest.mark.parametrize("field_name", INTEGER_FIELDS)
def test_changed_and_same_valued_integer_subclasses_refuse(field_name: str) -> None:
    policy = policy_module.CANONICAL_IB2_SOURCE_POLICY
    value = getattr(policy, field_name)
    with pytest.raises(policy_module.CanonicalIb2SourcePolicyError, match=field_name):
        replace(policy, **{field_name: value + 1})
    with pytest.raises(policy_module.CanonicalIb2SourcePolicyError, match=field_name):
        replace(policy, **{field_name: _IntSubclass(value)})
    with pytest.raises(policy_module.CanonicalIb2SourcePolicyError, match=field_name):
        replace(policy, **{field_name: float(value)})


@pytest.mark.parametrize("field_name", TUPLE_FIELDS)
def test_changed_and_same_valued_tuple_shapes_refuse(field_name: str) -> None:
    policy = policy_module.CANONICAL_IB2_SOURCE_POLICY
    value = getattr(policy, field_name)
    with pytest.raises(policy_module.CanonicalIb2SourcePolicyError, match=field_name):
        replace(policy, **{field_name: (*value, "changed")})
    with pytest.raises(policy_module.CanonicalIb2SourcePolicyError, match=field_name):
        replace(policy, **{field_name: list(value)})
    with pytest.raises(policy_module.CanonicalIb2SourcePolicyError, match=field_name):
        replace(policy, **{field_name: _TupleSubclass(value)})
    item_subclass = (_StringSubclass(value[0]), *value[1:])
    with pytest.raises(policy_module.CanonicalIb2SourcePolicyError, match=field_name):
        replace(policy, **{field_name: item_subclass})


@pytest.mark.parametrize("field_name", REQUIRED_TRUE_FIELDS)
def test_required_true_fields_reject_false_and_integer_one(field_name: str) -> None:
    policy = policy_module.CANONICAL_IB2_SOURCE_POLICY
    for invalid in (False, 1):
        with pytest.raises(
            policy_module.CanonicalIb2SourcePolicyError,
            match=field_name,
        ):
            replace(policy, **{field_name: invalid})


@pytest.mark.parametrize("field_name", REQUIRED_FALSE_FIELDS)
def test_required_false_fields_reject_true_and_integer_zero(field_name: str) -> None:
    policy = policy_module.CANONICAL_IB2_SOURCE_POLICY
    for invalid in (True, 0):
        with pytest.raises(
            policy_module.CanonicalIb2SourcePolicyError,
            match=field_name,
        ):
            replace(policy, **{field_name: invalid})


@pytest.mark.parametrize("field_name", UNBOUND_FIELDS)
def test_unbound_fields_reject_values_even_when_equal_to_none(field_name: str) -> None:
    policy = policy_module.CANONICAL_IB2_SOURCE_POLICY
    for invalid in ("bound", 0, _NoneEqual()):
        with pytest.raises(
            policy_module.CanonicalIb2SourcePolicyError,
            match=(
                "acceptance cutoff"
                if field_name == "global_acceptance_cutoff_utc"
                else field_name
            ),
        ):
            replace(policy, **{field_name: invalid})


def test_integer_zero_fields_reject_bool_false() -> None:
    policy = policy_module.CANONICAL_IB2_SOURCE_POLICY
    for field_name in (
        "current_external_request_budget",
        "authorized_outcome_looks",
        "consumed_outcome_looks",
    ):
        with pytest.raises(
            policy_module.CanonicalIb2SourcePolicyError,
            match=field_name,
        ):
            replace(policy, **{field_name: False})


@pytest.mark.parametrize("drift_kind", ["reordered", "duplicate"])
def test_period_inventory_rejects_interior_constant_drift(
    monkeypatch,
    drift_kind: str,
) -> None:
    periods = list(policy_module.CANONICAL_IB2_REQUIRED_PERIODS)
    if drift_kind == "reordered":
        periods[1], periods[2] = periods[2], periods[1]
    else:
        periods[2] = periods[1]
    drifted = tuple(periods)
    monkeypatch.setattr(
        policy_module,
        "CANONICAL_IB2_REQUIRED_PERIODS",
        drifted,
    )

    with pytest.raises(
        policy_module.CanonicalIb2SourcePolicyError,
        match="filing-quarter coverage is not exact",
    ):
        replace(
            policy_module.CANONICAL_IB2_SOURCE_POLICY,
            required_periods=drifted,
        )


def test_period_count_and_endpoints_reject_matching_constant_drift(
    monkeypatch,
) -> None:
    policy = policy_module.CANONICAL_IB2_SOURCE_POLICY
    monkeypatch.setattr(policy_module, "CANONICAL_IB2_SOURCE_EXPECTED_PERIOD_COUNT", 81)
    with pytest.raises(
        policy_module.CanonicalIb2SourcePolicyError,
        match="filing-quarter coverage is not exact",
    ):
        replace(policy, expected_period_count=81)

    monkeypatch.setattr(policy_module, "CANONICAL_IB2_SOURCE_EXPECTED_PERIOD_COUNT", 82)
    monkeypatch.setattr(policy_module, "CANONICAL_IB2_SOURCE_FIRST_PERIOD", "2005Q4")
    with pytest.raises(
        policy_module.CanonicalIb2SourcePolicyError,
        match="filing-quarter coverage is not exact",
    ):
        replace(policy, first_period="2005Q4")


@pytest.mark.parametrize(("field_name", "constant_name"), CONSTANT_BOUND_FIELDS)
def test_policy_refuses_matching_constant_and_field_drift(
    monkeypatch,
    field_name: str,
    constant_name: str,
) -> None:
    drifted = _alternate_value(field_name)
    monkeypatch.setattr(policy_module, constant_name, drifted)

    with pytest.raises(
        policy_module.CanonicalIb2SourcePolicyError,
        match="semantic fingerprint",
    ):
        replace(
            policy_module.CANONICAL_IB2_SOURCE_POLICY,
            **{field_name: drifted},
        )


def test_policy_is_frozen_and_payloads_are_fresh() -> None:
    policy = policy_module.CANONICAL_IB2_SOURCE_POLICY
    before = policy.to_payload()

    with pytest.raises(FrozenInstanceError):
        policy.source_mode = "live"  # type: ignore[misc]

    first = policy.to_payload()
    first["source_scope"]["required_periods"].append("2099Q4")
    first["authority"]["trading_authority"] = True

    assert policy.to_payload() == before
    assert policy.semantic_sha256 == policy_module.CANONICAL_IB2_SOURCE_POLICY_SHA256


def test_payload_and_literal_semantic_hash_are_stable() -> None:
    policy = policy_module.CANONICAL_IB2_SOURCE_POLICY
    payload = policy.to_payload()

    assert set(payload) == {
        "schema",
        "version",
        "governance_source",
        "governing_blueprint",
        "source_scope",
        "accession_evidence",
        "integrity_and_storage",
        "amendment_boundary",
        "future_retrieval_boundary",
        "unbound_inputs",
        "verification",
        "authority",
    }
    expected_hash = (
        "eec42a1e34b6200e0e195a6702307a5c716c10c40dbfd8e9e8095846c79e7dbe"
    )
    assert policy_module.CANONICAL_IB2_SOURCE_POLICY_SHA256 == expected_hash
    assert policy.semantic_sha256 == expected_hash
    assert hash_bytes((canonical_json(payload) + "\n").encode("utf-8")) == (
        expected_hash
    )


@pytest.mark.parametrize(
    "field_name",
    [field.name for field in fields(policy_module.CANONICAL_IB2_SOURCE_POLICY)],
)
def test_semantic_hash_binds_every_policy_field(field_name: str) -> None:
    policy = policy_module.CANONICAL_IB2_SOURCE_POLICY
    forged = copy.copy(policy)
    object.__setattr__(forged, field_name, _alternate_value(field_name))

    assert forged.semantic_sha256 != policy.semantic_sha256


def test_public_module_and_package_exports_are_explicit() -> None:
    expected = (
        "CANONICAL_IB2_REQUIRED_PERIODS",
        "CANONICAL_IB2_SOURCE_MODE",
        "CANONICAL_IB2_SOURCE_POLICY",
        "CANONICAL_IB2_SOURCE_POLICY_SHA256",
        "CANONICAL_IB2_SOURCE_POLICY_VERSION",
        "CanonicalIb2SourcePolicy",
        "CanonicalIb2SourcePolicyError",
    )

    assert tuple(policy_module.__all__) == expected
    for name in expected:
        assert getattr(insider_package, name) is getattr(policy_module, name)
        assert name in insider_package.__all__


def test_module_import_boundary_is_pure_and_no_io() -> None:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)

    assert imports == {"__future__", "dataclasses", "datetime", "data.hashing"}
    forbidden_names = {
        "open",
        "exec",
        "eval",
        "__import__",
        "compile",
        "input",
    }
    forbidden_attributes = {
        "import_module",
        "connect",
        "open",
        "read_bytes",
        "read_text",
        "write_bytes",
        "write_text",
        "request",
        "urlopen",
        "get",
        "post",
        "run",
        "Popen",
    }
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        assert not (
            isinstance(node.func, ast.Name)
            and node.func.id in forbidden_names
        )
        assert not (
            isinstance(node.func, ast.Attribute)
            and node.func.attr in forbidden_attributes
        )
    assert not any(
        isinstance(node, ast.Constant) and type(node.value) is float
        for node in ast.walk(tree)
    )
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "float"
        for node in ast.walk(tree)
    )


def test_construct_serialize_and_hash_do_not_open_files(monkeypatch) -> None:
    def refuse_open(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("policy attempted filesystem access")

    monkeypatch.setattr("builtins.open", refuse_open)
    policy = policy_module.CanonicalIb2SourcePolicy()

    assert policy.to_payload() == policy_module.CANONICAL_IB2_SOURCE_POLICY.to_payload()
    assert policy.semantic_sha256 == policy_module.CANONICAL_IB2_SOURCE_POLICY_SHA256
