"""Fixed local recovery diagnostics, with no I/O, retry or source authority.

Only exact controlled refusal types may expose one literal catalogue code.
External messages, dynamic type names, request objects, credentials, exception
properties and formatted exception representations are never projected. This
classifier cannot retrospectively determine an unrecorded failure's cause.
"""
from __future__ import annotations

import errno

from research.short_interest_etf.native_reported_anchor_cache import AnchorCacheRefusal
from scripts.capture_short_interest_count_recovery import RecoveryRefusal
from scripts.qualify_finra_short_interest import CapturePlatformRefusal, CaptureRefusal
from scripts.qualify_sharadar_companion import SharadarCaptureRefusal
from scripts.short_interest_keychain import ShortInterestKeychainError
from scripts.short_interest_lane_batch_guard import LaneBatchRefusal
from scripts.short_interest_refused_count_snapshot import RefusedSnapshotError


class RecoveryLocalRefusal(ValueError):
    """Successor controllers share this exact type without circular imports."""


# Explicit public codes, not a parser for arbitrary exception messages. Unknown
# future codes remain suppressed until a reviewed code change adds them here.
LOCAL_CONTRACT_CODES = frozenset("""
HTTP_after_START_window_refused START_clock_backdated START_window_exhausted_before_debit
attempt_budget_exhausted bounded_JSON_response_required chunk_closure_deadline_exceeded
chunk_final_audit_deadline_exceeded chunk_final_close_deadline_exceeded
chunk_final_membership_changed chunk_member_protection_or_size_changed chunk_member_short_read
chunk_membership_changed_or_negative_sibling chunk_original_member_changed
chunk_prior_member_changed_during_audit chunk_wall_time_exhausted closure_clock_refused
complete_composed_code_membership_required complete_exact_code_manifest_required
composed_code_custody_changed composed_code_exact_root_path_required composed_code_membership_changed
designated_runtime_driver_required empty_or_unaffordable_batch exact_chunk_operational_bindings
exact_chunk_registration exact_composed_code_custody_required exact_named_existing_key_required
exact_original_source_required fixed_chunk_output_must_be_ignored frozen_chunk_bounds
frozen_chunk_policy_changed new_claim_original_bytes_changed
prospective_bounded_protocol_pending_or_changed receipt_clock_refused refused_predecessor_debits_required
registered_code_bytes_changed response_echo_refused unregistered_composed_code_path
designated_lane_snapshot_required fixed_child_failure_diagnostic_changed
fixed_child_failure_receipt_changed fixed_child_started_sequence_required
fixed_historical_code_membership_changed fixed_historical_complete_code_identity_changed
fixed_negative_closure_or_debits_changed fixed_refusal_bytes_changed fixed_refused_inventory_shape_changed
fixed_refused_member_names_required fixed_spent_claim_bytes_changed only_fixed_original_historical_code
original_parent_code_not_lane_ancestor original_parent_exact_membership original_parent_membership_changed
prospectively_bound_manifest_changed prospectively_bound_manifest_digest_required
qualified_snapshot_manifest_cannot_be_rebound refused_child_START_mapping_changed
refused_child_code_not_lane_ancestor refused_child_inventory_accounting_changed
refused_child_observed_body_changed refused_child_protocol_changed refused_child_receipt_descriptor_changed
refused_child_spent_claim_lineage_changed refused_child_start_lineage_changed
refused_inventory_not_replayed registered_snapshot_member_required snapshot_bounded_read_required
snapshot_closed snapshot_custody_binding_changed snapshot_directory_changed snapshot_directory_link_refused
snapshot_directory_open_identity snapshot_directory_protection snapshot_full_member_stamp_changed
snapshot_full_membership_changed snapshot_lane_binding_changed snapshot_manifest_not_measured
snapshot_member_protection_or_bound snapshot_member_read_bound snapshot_member_short_read
snapshot_named_member_changed snapshot_open_member_changed snapshot_original_member_bytes_changed
snapshot_spent_claim_changed snapshot_typed_inventory_rebound
exact_zero_start_source_bindings zero_start_actual_clocks_required zero_start_claim_lineage_changed
zero_start_closed_directory_changed zero_start_exact_historical_code_membership
zero_start_exact_negative_membership_required zero_start_frozen_control_hashes_required
zero_start_historical_code_changed zero_start_negative_or_debits_changed zero_start_original_bytes_changed
zero_start_predecessor_binding_changed zero_start_never_source_or_readiness_authority
Git_root_changed all_named_publication_slots_consumed batch_not_open_or_halted bound_parallel_plan_changed
bounded_batch_gate_changed bounded_batch_state_changed designated_physical_root_changed
dirty_or_unrecognized_status_entry drain_all_started_slots_before_new_batch exact_bound_source_ticket_required
exact_frozen_sequence_not_completed exact_lane_and_parallel_plan_required exact_physical_root_path
finite_one_active_HTTP_batch_required finite_one_shot_publication_batch_required fixed_lane_roots_and_hashes_required
halted_batch_cannot_restart halted_batch_must_drain_every_started_slot lane_Git_result_refused
lane_Git_unavailable lane_HEAD_or_branch_changed lane_changed_during_remote_read lane_evidence_changed
lane_evidence_factory_required lane_guard_changed lane_upstream_changed matching_actual_remote_advanced_or_ambiguous
next_exact_query_prefix_required one_of_eight_exact_ticket_instances_required one_shot_bounded_HTTP_slot_required
one_shot_named_publication_only one_started_slot_one_drain only_active_started_ticket_can_drain
open_HTTP_batch_required porcelain_disabled_counts_shape porcelain_header_changed porcelain_status_shape
porcelain_status_encoding publication_batch_not_open_or_halted publication_batch_required halted_batch_drained_no_completion
cache_creator_not_lane_ancestor cache_exact_five_file_inventory cache_path_creator_and_closure_registration_pending
cache_target_not_ignored cache_writer_protocol_not_prospectively_registered canonical_source_preflight_required
complete_registered_historical_creator_manifest count_output_not_ignored count_protocol_pending_before_new_output
current_code_not_exact_committed_manifest custody_file_protection custody_parent_open_identity
custody_parent_protection custody_path_symlink_or_relative exact_original_archive_aliases finite_exact_custody_file_list
guarded_cache_Git_refused held_cache_exact_five_file_inventory_changed held_custody_binding_changed
held_custody_file_changed held_custody_parent_changed held_custody_parent_symlink held_read_exact_bound_file
held_read_limit held_read_original_length historical_creator_blob_changed inventory_directory_changed_during_scan
inventory_directory_fd_required inventory_fresh_directory_identity_changed inventory_owned_directory_required
new_exclusive_cache_bytes_differ_from_verified_plan original_archive_aliases_match_exact_plan
registered_cache_context_changed registered_cache_context_factory_required registered_cache_creator_protocol
registered_original_TICKERS_archive_bytes unchanged_completed_source_closure
descriptor_headroom_unverifiable insufficient_preclaim_descriptor_headroom
control_JSON_refused control_bytes_required duplicate_control_key
keychain_credential_format_refused keychain_credential_serialization_refused keychain_response_type_refused
macos_login_keychain_required owner_keychain_path_refused owner_keychain_parent_refused
owner_keychain_path_unavailable unknown_owner_keychain_item owner_keychain_access_unavailable
owner_keychain_item_unavailable protected_capture_platform_unavailable
duplicate_json_key nonfinite_json git_guard_failed invalid_expected_head wrong_physical_root wrong_git_root
wrong_branch head_changed dirty_worktree credential_symlink credential_directory_protection credential_file_protection
credential_fields credential_value artifact_already_exists artifact_protection capture_symlink capture_directory_protection
credential_echo credential_location_or_symlink response_contract_refused content_type response_size_limit
invalid_expected_remote remote_advanced_or_ambiguous request_inventory http_not_200 network_failure
""".split())

_CONTROLLED_TYPES = (
    (RecoveryLocalRefusal, "local_contract_refusal"),
    (RecoveryRefusal, "local_contract_refusal"),
    (RefusedSnapshotError, "local_contract_refusal"),
    (AnchorCacheRefusal, "local_contract_refusal"),
    (LaneBatchRefusal, "lane_guard_refusal"),
    (CapturePlatformRefusal, "platform_refusal"),
    (CaptureRefusal, "local_contract_refusal"),
    (SharadarCaptureRefusal, "local_contract_refusal"),
    (ShortInterestKeychainError, "keychain_refusal"),
)
_ERRNO_NAMES = ("EACCES", "EPERM", "EMFILE", "ENFILE", "ENOSPC", "ENOMEM", "ENOENT", "EIO", "ETIMEDOUT")


def _contract_code(error) -> str | None:
    # Invoked only for exact controlled classes. The base descriptor bypasses
    # arbitrary args/code properties; no arbitrary args object is formatted.
    arguments = BaseException.args.__get__(error, BaseException)
    if type(arguments) is not tuple or len(arguments) != 1 or type(arguments[0]) is not str:
        return None
    value = arguments[0]
    if len(value) > 256:
        return None
    code = value.removeprefix("REFUSED: ")
    return code if code in LOCAL_CONTRACT_CODES else None


def _errno_name(error) -> str | None:
    number = OSError.errno.__get__(error, OSError)
    if type(number) is not int:
        return None
    for name in _ERRNO_NAMES:
        value = getattr(errno, name, None)
        if type(value) is int and number == value:
            return name
    return None


def fixed_local_failure(error) -> dict:
    """Project one fixed local category, optional errno and catalogue code.

    No supplied property, cause, context, reason, URL, body or request is
    inspected. A local timeout is not HTTP failure classification and grants
    no retry permission. The returned mapping never contains the exception.
    """
    error_type = type(error)
    for controlled_type, category in _CONTROLLED_TYPES:
        if error_type is controlled_type:
            return {"category": category, "errno_name": None, "contract_code": _contract_code(error)}
    # Bypass a hostile metaclass's __mro__/name properties and avoid isinstance
    # consulting a supplied object's overridden __class__ property.
    bases = type.__getattribute__(error_type, "__mro__")
    for base, category in ((TypeError, "local_type_error"), (NameError, "local_name_error"),
                           (MemoryError, "local_memory_error"), (TimeoutError, "local_timeout")):
        if any(ancestor is base for ancestor in bases):
            return {"category": category,
                    "errno_name": _errno_name(error) if base is TimeoutError else None,
                    "contract_code": None}
    if any(ancestor is OSError for ancestor in bases):
        return {"category": "local_os_error", "errno_name": _errno_name(error), "contract_code": None}
    return {"category": "unknown_local_error", "errno_name": None, "contract_code": None}
