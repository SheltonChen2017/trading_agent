"""Zero-access canonical IB-2 source-input policy.

This module freezes the owner's selected source mode and filing-quarter
coverage before any real manifest or filing artifact is supplied.  It performs
no filesystem access, discovery, download, parsing, provider call, outcome
join, QuantConnect work, deployment, or execution.  The singleton therefore
describes required future evidence; it does not certify that such evidence
exists or that canonical IB-2 is complete.

The corpus boundary is the inclusive SEC bulk-package range 2006Q1 through
2026Q2, partitioned by ``SUBMISSION.FILING_DATE``.  It is deliberately not a
global EDGAR acceptance timestamp.  Public availability remains an exact
per-accession fact supplied by a later reviewed evidence boundary.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from data.hashing import canonical_json, hash_bytes


CANONICAL_IB2_SOURCE_POLICY_VERSION = (
    "INSETF-IB2-CANONICAL-SOURCE-POLICY-v1"
)
CANONICAL_IB2_SOURCE_POLICY_SCHEMA = (
    "insider-buying-canonical-source-policy-v1"
)
CANONICAL_IB2_SOURCE_DIRECTIVE_ID = (
    "owner-selected-canonical-ib2-source-2026-09-18"
)
CANONICAL_IB2_SOURCE_DIRECTIVE_PATH = (
    "docs/Strategy Description/INSIDER_BUYING_IMPLEMENTATION_RECORD.md"
)
CANONICAL_IB2_SOURCE_DIRECTIVE_COMMIT = (
    "2b4c0b9525dd9049d67672daf8abf9961b682029"
)
CANONICAL_IB2_SOURCE_DIRECTIVE_EFFECTIVE_DATE = date(2026, 9, 18)
CANONICAL_IB2_SOURCE_BLUEPRINT_PATH = (
    "docs/Strategy Description/INSIDER_BUYING_ETF_STRATEGY_BLUEPRINT.pdf"
)
CANONICAL_IB2_SOURCE_BLUEPRINT_SHA256 = (
    "f8834e13bb22d63a1a5a055a24cc2638ecb2e535b733c1fdd1741a28c65db88c"
)

CANONICAL_IB2_SOURCE_MODE = "owner_supplied_immutable_offline_snapshot"
CANONICAL_IB2_SOURCE_FIRST_PERIOD = "2006Q1"
CANONICAL_IB2_SOURCE_LAST_PERIOD = "2026Q2"
CANONICAL_IB2_SOURCE_FIRST_FILING_DATE = date(2006, 1, 1)
CANONICAL_IB2_SOURCE_LAST_FILING_DATE = date(2026, 6, 30)
CANONICAL_IB2_SOURCE_PARTITION_FIELD = "SUBMISSION.FILING_DATE"
CANONICAL_IB2_SOURCE_EXPECTED_PERIOD_COUNT = 82
CANONICAL_IB2_GLOBAL_ACCEPTANCE_CUTOFF_POLICY = (
    "none-per-accession-public-availability-only"
)
CANONICAL_IB2_QUARTER_COVERAGE_POLICY = (
    "exact-contiguous-inclusive-no-missing-duplicate-reordered-or-extra-periods"
)
CANONICAL_IB2_ACCESSION_COVERAGE_POLICY = (
    "exactly-one-acceptance-metadata-and-one-complete-primary-ownership-xml-"
    "per-bulk-form4-or-form4a-accession-no-missing-extra-duplicate-conflict-"
    "or-cross-accession-match"
)
CANONICAL_IB2_AVAILABILITY_POLICY = (
    "exact-edgar-acceptance-per-accession-never-transaction-bulk-publication-"
    "or-retrieval-time"
)
CANONICAL_IB2_AMENDMENT_POLICY = (
    "retain-every-as-filed-version-no-simultaneous-original-amendment-count-"
    "and-quarantine-unresolved-families"
)
CANONICAL_IB2_CACHE_POLICY = (
    "content-addressed-atomic-immutable-portable-no-overwrite"
)
CANONICAL_IB2_REVISION_POLICY = "new-evidence-epoch-never-in-place-mutation"
CANONICAL_IB2_HASH_ALGORITHM = "sha256"
CANONICAL_IB2_CURRENT_REQUEST_BUDGET = 0
CANONICAL_IB2_FUTURE_INTERNAL_REQUESTS_PER_SECOND_CEILING = 5


def _required_periods() -> tuple[str, ...]:
    return tuple(
        f"{year}Q{quarter}"
        for year in range(2006, 2027)
        for quarter in range(1, 5)
        if (year, quarter) <= (2026, 2)
    )


CANONICAL_IB2_REQUIRED_PERIODS = _required_periods()
CANONICAL_IB2_ACCESSION_DOCUMENT_TYPES = ("4", "4/A")
CANONICAL_IB2_CONTEXT_DOCUMENT_TYPES = ("3", "5")
CANONICAL_IB2_REQUIRED_ACCESSION_ARTIFACTS = (
    "acceptance_metadata",
    "complete_primary_ownership_xml",
)
CANONICAL_IB2_HASH_BOUND_OBJECTS = (
    "raw_quarter_zip",
    "raw_zip_member",
    "parsed_quarter_identity",
    "acceptance_metadata_artifact",
    "primary_ownership_xml_artifact",
    "canonical_ordered_period_inventory",
    "canonical_ordered_accession_inventory",
)
CANONICAL_IB2_AMENDMENT_QUARANTINE_REASONS = (
    "unresolved",
    "missing_original",
    "ambiguous",
    "branching",
    "cyclic",
    "cross_issuer",
    "temporally_reversed",
)


class CanonicalIb2SourcePolicyError(ValueError):
    """The frozen canonical IB-2 source-input policy failed closed."""


@dataclass(frozen=True)
class CanonicalIb2SourcePolicy:
    """Immutable owner-selected policy with every real-data gate still shut."""

    version: str = CANONICAL_IB2_SOURCE_POLICY_VERSION
    schema: str = CANONICAL_IB2_SOURCE_POLICY_SCHEMA
    directive_id: str = CANONICAL_IB2_SOURCE_DIRECTIVE_ID
    directive_path: str = CANONICAL_IB2_SOURCE_DIRECTIVE_PATH
    directive_commit: str = CANONICAL_IB2_SOURCE_DIRECTIVE_COMMIT
    directive_effective_date: date = (
        CANONICAL_IB2_SOURCE_DIRECTIVE_EFFECTIVE_DATE
    )
    blueprint_path: str = CANONICAL_IB2_SOURCE_BLUEPRINT_PATH
    blueprint_sha256: str = CANONICAL_IB2_SOURCE_BLUEPRINT_SHA256

    source_mode: str = CANONICAL_IB2_SOURCE_MODE
    first_period: str = CANONICAL_IB2_SOURCE_FIRST_PERIOD
    last_period: str = CANONICAL_IB2_SOURCE_LAST_PERIOD
    first_filing_date: date = CANONICAL_IB2_SOURCE_FIRST_FILING_DATE
    last_filing_date: date = CANONICAL_IB2_SOURCE_LAST_FILING_DATE
    partition_field: str = CANONICAL_IB2_SOURCE_PARTITION_FIELD
    expected_period_count: int = CANONICAL_IB2_SOURCE_EXPECTED_PERIOD_COUNT
    required_periods: tuple[str, ...] = CANONICAL_IB2_REQUIRED_PERIODS
    quarter_coverage_policy: str = CANONICAL_IB2_QUARTER_COVERAGE_POLICY
    global_acceptance_cutoff_utc: None = None
    global_acceptance_cutoff_policy: str = (
        CANONICAL_IB2_GLOBAL_ACCEPTANCE_CUTOFF_POLICY
    )
    availability_policy: str = CANONICAL_IB2_AVAILABILITY_POLICY

    one_raw_zip_per_quarter_required: bool = True
    accession_document_types: tuple[str, ...] = (
        CANONICAL_IB2_ACCESSION_DOCUMENT_TYPES
    )
    context_document_types: tuple[str, ...] = CANONICAL_IB2_CONTEXT_DOCUMENT_TYPES
    required_accession_artifacts: tuple[str, ...] = (
        CANONICAL_IB2_REQUIRED_ACCESSION_ARTIFACTS
    )
    accession_coverage_policy: str = CANONICAL_IB2_ACCESSION_COVERAGE_POLICY
    form3_and_form5_are_context_only: bool = True
    form3_or_form5_canonical_candidate_authorized: bool = False

    hash_algorithm: str = CANONICAL_IB2_HASH_ALGORITHM
    hash_bound_objects: tuple[str, ...] = CANONICAL_IB2_HASH_BOUND_OBJECTS
    exact_byte_sizes_required: bool = True
    canonical_ordered_manifest_required: bool = True
    cache_policy: str = CANONICAL_IB2_CACHE_POLICY
    exact_retry_is_idempotent: bool = True
    conflicting_content_refused: bool = True
    revision_policy: str = CANONICAL_IB2_REVISION_POLICY

    amendment_policy: str = CANONICAL_IB2_AMENDMENT_POLICY
    retain_every_as_filed_version: bool = True
    simultaneous_original_and_amendment_counting_authorized: bool = False
    amendment_quarantine_reasons: tuple[str, ...] = (
        CANONICAL_IB2_AMENDMENT_QUARANTINE_REASONS
    )

    current_external_request_budget: int = CANONICAL_IB2_CURRENT_REQUEST_BUDGET
    future_internal_requests_per_second_ceiling: int = (
        CANONICAL_IB2_FUTURE_INTERNAL_REQUESTS_PER_SECOND_CEILING
    )
    future_identifying_contact_required: bool = True
    future_accession_cache_required: bool = True
    future_backoff_and_checkpointing_required: bool = True
    future_backtest_network_requests_authorized: bool = False

    source_manifest_id: None = None
    source_manifest_sha256: None = None
    official_schema_profile_id: None = None
    official_schema_profile_sha256: None = None
    amendment_link_inventory_id: None = None
    amendment_link_inventory_sha256: None = None
    title_exception_dictionary_id: None = None
    title_exception_dictionary_sha256: None = None
    normalized_role_taxonomy_id: None = None
    normalized_role_taxonomy_sha256: None = None
    pit_security_master_id: None = None
    pit_security_master_sha256: None = None
    durable_qc_symbol_id_namespace: None = None
    calendar_session_map_id: None = None
    calendar_session_map_sha256: None = None

    real_artifact_read_authorized: bool = False
    source_manifest_bound: bool = False
    official_sec_source_authenticated: bool = False
    official_schema_profile_verified: bool = False
    form4_accession_coverage_verified: bool = False
    amendment_linkage_verified: bool = False
    complete_amendment_coverage_verified: bool = False
    authenticated_supersession_authorized: bool = False
    title_exception_dictionary_verified: bool = False
    normalized_role_taxonomy_verified: bool = False
    official_pit_security_master_verified: bool = False
    durable_qc_symbol_id_verified: bool = False
    trading_calendar_session_mapping_verified: bool = False
    canonical_filtering_authorized: bool = False
    canonical_deduplication_authorized: bool = False
    canonical_aggregation_authorized: bool = False
    canonical_scoring_authorized: bool = False
    canonical_ib2_complete: bool = False

    authorized_outcome_looks: int = 0
    consumed_outcome_looks: int = 0
    network_access_authorized: bool = False
    sec_access_authorized: bool = False
    provider_access_authorized: bool = False
    credential_access_authorized: bool = False
    licensed_row_access_authorized: bool = False
    outcome_access_authorized: bool = False
    qc_upload_authorized: bool = False
    qc_processing_authorized: bool = False
    qc_job_authorized: bool = False
    qc_backtest_authorized: bool = False
    broker_access_authorized: bool = False
    operator_database_access_authorized: bool = False
    scheduler_access_authorized: bool = False
    paper_trading_authorized: bool = False
    live_trading_authorized: bool = False
    deployment_authorized: bool = False
    capital_authorized: bool = False
    order_authorized: bool = False
    trading_authority: bool = False

    def __post_init__(self) -> None:
        for field_name, value, expected in (
            ("version", self.version, CANONICAL_IB2_SOURCE_POLICY_VERSION),
            ("schema", self.schema, CANONICAL_IB2_SOURCE_POLICY_SCHEMA),
            ("directive_id", self.directive_id, CANONICAL_IB2_SOURCE_DIRECTIVE_ID),
            (
                "directive_path",
                self.directive_path,
                CANONICAL_IB2_SOURCE_DIRECTIVE_PATH,
            ),
            (
                "directive_commit",
                self.directive_commit,
                CANONICAL_IB2_SOURCE_DIRECTIVE_COMMIT,
            ),
            (
                "blueprint_path",
                self.blueprint_path,
                CANONICAL_IB2_SOURCE_BLUEPRINT_PATH,
            ),
            (
                "blueprint_sha256",
                self.blueprint_sha256,
                CANONICAL_IB2_SOURCE_BLUEPRINT_SHA256,
            ),
            ("source_mode", self.source_mode, CANONICAL_IB2_SOURCE_MODE),
            ("first_period", self.first_period, CANONICAL_IB2_SOURCE_FIRST_PERIOD),
            ("last_period", self.last_period, CANONICAL_IB2_SOURCE_LAST_PERIOD),
            (
                "partition_field",
                self.partition_field,
                CANONICAL_IB2_SOURCE_PARTITION_FIELD,
            ),
            (
                "quarter_coverage_policy",
                self.quarter_coverage_policy,
                CANONICAL_IB2_QUARTER_COVERAGE_POLICY,
            ),
            (
                "global_acceptance_cutoff_policy",
                self.global_acceptance_cutoff_policy,
                CANONICAL_IB2_GLOBAL_ACCEPTANCE_CUTOFF_POLICY,
            ),
            (
                "availability_policy",
                self.availability_policy,
                CANONICAL_IB2_AVAILABILITY_POLICY,
            ),
            (
                "accession_coverage_policy",
                self.accession_coverage_policy,
                CANONICAL_IB2_ACCESSION_COVERAGE_POLICY,
            ),
            ("hash_algorithm", self.hash_algorithm, CANONICAL_IB2_HASH_ALGORITHM),
            ("cache_policy", self.cache_policy, CANONICAL_IB2_CACHE_POLICY),
            ("revision_policy", self.revision_policy, CANONICAL_IB2_REVISION_POLICY),
            (
                "amendment_policy",
                self.amendment_policy,
                CANONICAL_IB2_AMENDMENT_POLICY,
            ),
        ):
            if type(value) is not str or value != expected:
                raise CanonicalIb2SourcePolicyError(
                    f"REFUSED: {field_name} changed from the owner-selected policy"
                )

        for field_name, value, expected in (
            (
                "directive_effective_date",
                self.directive_effective_date,
                CANONICAL_IB2_SOURCE_DIRECTIVE_EFFECTIVE_DATE,
            ),
            (
                "first_filing_date",
                self.first_filing_date,
                CANONICAL_IB2_SOURCE_FIRST_FILING_DATE,
            ),
            (
                "last_filing_date",
                self.last_filing_date,
                CANONICAL_IB2_SOURCE_LAST_FILING_DATE,
            ),
        ):
            if type(value) is not date or value != expected:
                raise CanonicalIb2SourcePolicyError(
                    f"REFUSED: {field_name} changed from the owner-selected policy"
                )

        for field_name, value, expected in (
            (
                "expected_period_count",
                self.expected_period_count,
                CANONICAL_IB2_SOURCE_EXPECTED_PERIOD_COUNT,
            ),
            (
                "current_external_request_budget",
                self.current_external_request_budget,
                CANONICAL_IB2_CURRENT_REQUEST_BUDGET,
            ),
            (
                "future_internal_requests_per_second_ceiling",
                self.future_internal_requests_per_second_ceiling,
                CANONICAL_IB2_FUTURE_INTERNAL_REQUESTS_PER_SECOND_CEILING,
            ),
            ("authorized_outcome_looks", self.authorized_outcome_looks, 0),
            ("consumed_outcome_looks", self.consumed_outcome_looks, 0),
        ):
            if type(value) is not int or value != expected:
                raise CanonicalIb2SourcePolicyError(
                    f"REFUSED: {field_name} changed from the exact integer policy"
                )

        for field_name, value, expected in (
            ("required_periods", self.required_periods, CANONICAL_IB2_REQUIRED_PERIODS),
            (
                "accession_document_types",
                self.accession_document_types,
                CANONICAL_IB2_ACCESSION_DOCUMENT_TYPES,
            ),
            (
                "context_document_types",
                self.context_document_types,
                CANONICAL_IB2_CONTEXT_DOCUMENT_TYPES,
            ),
            (
                "required_accession_artifacts",
                self.required_accession_artifacts,
                CANONICAL_IB2_REQUIRED_ACCESSION_ARTIFACTS,
            ),
            (
                "hash_bound_objects",
                self.hash_bound_objects,
                CANONICAL_IB2_HASH_BOUND_OBJECTS,
            ),
            (
                "amendment_quarantine_reasons",
                self.amendment_quarantine_reasons,
                CANONICAL_IB2_AMENDMENT_QUARANTINE_REASONS,
            ),
        ):
            if (
                type(value) is not tuple
                or any(type(item) is not str for item in value)
                or value != expected
            ):
                raise CanonicalIb2SourcePolicyError(
                    f"REFUSED: {field_name} changed from the exact tuple policy"
                )

        if (
            self.required_periods != _required_periods()
            or len(self.required_periods) != self.expected_period_count
            or self.required_periods[0] != self.first_period
            or self.required_periods[-1] != self.last_period
        ):
            raise CanonicalIb2SourcePolicyError(
                "REFUSED: required filing-quarter coverage is not exact"
            )
        if self.global_acceptance_cutoff_utc is not None:
            raise CanonicalIb2SourcePolicyError(
                "REFUSED: no corpus-wide EDGAR acceptance cutoff is authorized"
            )

        for field_name in (
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
        ):
            value = getattr(self, field_name)
            if type(value) is not bool or not value:
                raise CanonicalIb2SourcePolicyError(
                    f"REFUSED: {field_name} must remain true"
                )

        for field_name in (
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
        ):
            if getattr(self, field_name) is not None:
                raise CanonicalIb2SourcePolicyError(
                    f"REFUSED: {field_name} remains unbound"
                )

        for field_name in (
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
        ):
            value = getattr(self, field_name)
            if type(value) is not bool or value:
                raise CanonicalIb2SourcePolicyError(
                    f"REFUSED: {field_name} must remain false"
                )

        payload = (canonical_json(self.to_payload()) + "\n").encode("utf-8")
        if hash_bytes(payload) != (
            "eec42a1e34b6200e0e195a6702307a5c716c10c40dbfd8e9e8095846c79e7dbe"
        ):
            raise CanonicalIb2SourcePolicyError(
                "REFUSED: canonical IB-2 source-policy semantic fingerprint "
                "changed"
            )

    def to_payload(self) -> dict[str, object]:
        """Return a fresh canonical-JSON-safe policy representation."""

        return {
            "schema": self.schema,
            "version": self.version,
            "governance_source": {
                "directive_id": self.directive_id,
                "path": self.directive_path,
                "source_commit": self.directive_commit,
                "effective_date": self.directive_effective_date.isoformat(),
            },
            "governing_blueprint": {
                "path": self.blueprint_path,
                "sha256": self.blueprint_sha256,
            },
            "source_scope": {
                "mode": self.source_mode,
                "first_period": self.first_period,
                "last_period": self.last_period,
                "first_filing_date": self.first_filing_date.isoformat(),
                "last_filing_date": self.last_filing_date.isoformat(),
                "partition_field": self.partition_field,
                "expected_period_count": self.expected_period_count,
                "required_periods": list(self.required_periods),
                "quarter_coverage_policy": self.quarter_coverage_policy,
                "global_acceptance_cutoff_utc": (
                    self.global_acceptance_cutoff_utc
                ),
                "global_acceptance_cutoff_policy": (
                    self.global_acceptance_cutoff_policy
                ),
                "availability_policy": self.availability_policy,
            },
            "accession_evidence": {
                "one_raw_zip_per_quarter_required": (
                    self.one_raw_zip_per_quarter_required
                ),
                "accession_document_types": list(self.accession_document_types),
                "context_document_types": list(self.context_document_types),
                "required_accession_artifacts": list(
                    self.required_accession_artifacts
                ),
                "accession_coverage_policy": self.accession_coverage_policy,
                "form3_and_form5_are_context_only": (
                    self.form3_and_form5_are_context_only
                ),
                "form3_or_form5_canonical_candidate_authorized": (
                    self.form3_or_form5_canonical_candidate_authorized
                ),
            },
            "integrity_and_storage": {
                "hash_algorithm": self.hash_algorithm,
                "hash_bound_objects": list(self.hash_bound_objects),
                "exact_byte_sizes_required": self.exact_byte_sizes_required,
                "canonical_ordered_manifest_required": (
                    self.canonical_ordered_manifest_required
                ),
                "cache_policy": self.cache_policy,
                "exact_retry_is_idempotent": self.exact_retry_is_idempotent,
                "conflicting_content_refused": self.conflicting_content_refused,
                "revision_policy": self.revision_policy,
            },
            "amendment_boundary": {
                "policy": self.amendment_policy,
                "retain_every_as_filed_version": (
                    self.retain_every_as_filed_version
                ),
                "simultaneous_original_and_amendment_counting_authorized": (
                    self.simultaneous_original_and_amendment_counting_authorized
                ),
                "quarantine_reasons": list(self.amendment_quarantine_reasons),
            },
            "future_retrieval_boundary": {
                "current_external_request_budget": (
                    self.current_external_request_budget
                ),
                "future_internal_requests_per_second_ceiling": (
                    self.future_internal_requests_per_second_ceiling
                ),
                "future_identifying_contact_required": (
                    self.future_identifying_contact_required
                ),
                "future_accession_cache_required": (
                    self.future_accession_cache_required
                ),
                "future_backoff_and_checkpointing_required": (
                    self.future_backoff_and_checkpointing_required
                ),
                "future_backtest_network_requests_authorized": (
                    self.future_backtest_network_requests_authorized
                ),
            },
            "unbound_inputs": {
                "source_manifest_id": self.source_manifest_id,
                "source_manifest_sha256": self.source_manifest_sha256,
                "official_schema_profile_id": self.official_schema_profile_id,
                "official_schema_profile_sha256": (
                    self.official_schema_profile_sha256
                ),
                "amendment_link_inventory_id": self.amendment_link_inventory_id,
                "amendment_link_inventory_sha256": (
                    self.amendment_link_inventory_sha256
                ),
                "title_exception_dictionary_id": (
                    self.title_exception_dictionary_id
                ),
                "title_exception_dictionary_sha256": (
                    self.title_exception_dictionary_sha256
                ),
                "normalized_role_taxonomy_id": self.normalized_role_taxonomy_id,
                "normalized_role_taxonomy_sha256": (
                    self.normalized_role_taxonomy_sha256
                ),
                "pit_security_master_id": self.pit_security_master_id,
                "pit_security_master_sha256": self.pit_security_master_sha256,
                "durable_qc_symbol_id_namespace": (
                    self.durable_qc_symbol_id_namespace
                ),
                "calendar_session_map_id": self.calendar_session_map_id,
                "calendar_session_map_sha256": self.calendar_session_map_sha256,
            },
            "verification": {
                "real_artifact_read_authorized": self.real_artifact_read_authorized,
                "source_manifest_bound": self.source_manifest_bound,
                "official_sec_source_authenticated": (
                    self.official_sec_source_authenticated
                ),
                "official_schema_profile_verified": (
                    self.official_schema_profile_verified
                ),
                "form4_accession_coverage_verified": (
                    self.form4_accession_coverage_verified
                ),
                "amendment_linkage_verified": self.amendment_linkage_verified,
                "complete_amendment_coverage_verified": (
                    self.complete_amendment_coverage_verified
                ),
                "title_exception_dictionary_verified": (
                    self.title_exception_dictionary_verified
                ),
                "normalized_role_taxonomy_verified": (
                    self.normalized_role_taxonomy_verified
                ),
                "official_pit_security_master_verified": (
                    self.official_pit_security_master_verified
                ),
                "durable_qc_symbol_id_verified": (
                    self.durable_qc_symbol_id_verified
                ),
                "trading_calendar_session_mapping_verified": (
                    self.trading_calendar_session_mapping_verified
                ),
                "canonical_ib2_complete": self.canonical_ib2_complete,
            },
            "authority": {
                "authenticated_supersession_authorized": (
                    self.authenticated_supersession_authorized
                ),
                "canonical_filtering_authorized": (
                    self.canonical_filtering_authorized
                ),
                "canonical_deduplication_authorized": (
                    self.canonical_deduplication_authorized
                ),
                "canonical_aggregation_authorized": (
                    self.canonical_aggregation_authorized
                ),
                "canonical_scoring_authorized": self.canonical_scoring_authorized,
                "authorized_outcome_looks": self.authorized_outcome_looks,
                "consumed_outcome_looks": self.consumed_outcome_looks,
                "network_access_authorized": self.network_access_authorized,
                "sec_access_authorized": self.sec_access_authorized,
                "provider_access_authorized": self.provider_access_authorized,
                "credential_access_authorized": self.credential_access_authorized,
                "licensed_row_access_authorized": (
                    self.licensed_row_access_authorized
                ),
                "outcome_access_authorized": self.outcome_access_authorized,
                "qc_upload_authorized": self.qc_upload_authorized,
                "qc_processing_authorized": self.qc_processing_authorized,
                "qc_job_authorized": self.qc_job_authorized,
                "qc_backtest_authorized": self.qc_backtest_authorized,
                "broker_access_authorized": self.broker_access_authorized,
                "operator_database_access_authorized": (
                    self.operator_database_access_authorized
                ),
                "scheduler_access_authorized": self.scheduler_access_authorized,
                "paper_trading_authorized": self.paper_trading_authorized,
                "live_trading_authorized": self.live_trading_authorized,
                "deployment_authorized": self.deployment_authorized,
                "capital_authorized": self.capital_authorized,
                "order_authorized": self.order_authorized,
                "trading_authority": self.trading_authority,
            },
        }

    @property
    def semantic_sha256(self) -> str:
        payload = (canonical_json(self.to_payload()) + "\n").encode("utf-8")
        return hash_bytes(payload)


CANONICAL_IB2_SOURCE_POLICY = CanonicalIb2SourcePolicy()
CANONICAL_IB2_SOURCE_POLICY_SHA256 = (
    CANONICAL_IB2_SOURCE_POLICY.semantic_sha256
)


__all__ = [
    "CANONICAL_IB2_REQUIRED_PERIODS",
    "CANONICAL_IB2_SOURCE_MODE",
    "CANONICAL_IB2_SOURCE_POLICY",
    "CANONICAL_IB2_SOURCE_POLICY_SHA256",
    "CANONICAL_IB2_SOURCE_POLICY_VERSION",
    "CanonicalIb2SourcePolicy",
    "CanonicalIb2SourcePolicyError",
]
