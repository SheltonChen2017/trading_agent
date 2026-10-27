"""Observed AE metadata for an independently gated QC-native source candidate.

No source/control read, credentials, project or run authority is provided.
"""
from __future__ import annotations
import hashlib
import json

SCHEMA = 'arv2-r298-ae-native-source-spec-binding-v1'
_FACT_JSON = b"{\"caller_sha256\":\"501371b38ab01fd23262b13da9432b6356dfa65a93ef27132992947307884673\",\"expected_head\":\"d49e54152f4d2bba50161850c82d692af1c7fc3c\",\"producer\":{\"actual_exit\":0,\"bound\":null,\"completion_observed_at\":\"2026-10-27T10:01:16.942247Z\",\"dispatched_at\":\"2026-10-27T10:01:13.648410Z\",\"spawn_observed\":true,\"stderr_bytes\":0,\"stderr_sha256\":\"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855\",\"stdout_bytes\":4926,\"stdout_sha256\":\"c3b5c94b504527a330ff5351621e59860b9236d7b73eea45d88ddc4bc989e886\"},\"profile_sha256\":\"92c66527dc99a842726a9dce5dddfc43e91537d5531ad632ce71276442e1af8d\",\"report\":{\"byte_count\":4797,\"sha256\":\"dc9d728d3dcb61f6393d82b22c7c9a05b06b1995ea0922fa965eb151fe59b010\"},\"schema\":\"arv2-r298-native-five-source-specification-ae-v1\",\"specification_file\":{\"byte_count\":1791,\"relative_path\":\"artifacts/analyst_revisions_v2/newrule_native_price_spec/R326-20261027-AE/native-price-specification.json\",\"sha256\":\"9da6813b4807d7ebf0ea32fddd38ab0740ff6c6edbc3bd05cdc5889775eb1f66\"},\"validator\":{\"actual_exit\":0,\"bound\":null,\"completion_observed_at\":\"2026-10-27T10:01:20.093562Z\",\"dispatched_at\":\"2026-10-27T10:01:16.942418Z\",\"spawn_observed\":true,\"stderr_bytes\":0,\"stderr_sha256\":\"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855\",\"stdout_bytes\":4926,\"stdout_sha256\":\"c3b5c94b504527a330ff5351621e59860b9236d7b73eea45d88ddc4bc989e886\"}}"
_SPEC_JSON = b"{\"NYSE_schedule_sha256\":\"d4bc21d601f7d32b2b4190fe1ce4307d2a63d56821d61d99464dbd710b7476ee\",\"activation_sha256\":\"ffdc80e1b6e76410ddd4840e5a21e49aea1dbdd5c735b6bcbd88bfe832e0233b\",\"binding_stream_sha256\":\"73ba4ac73c0485b2d274c31b5ec740a97a64de27a4f6dfbfb9cb63bc8e7cd15f\",\"calendar_commitment\":\"canonical_ASCII_NO_LF_rows_session_open_utc_close_utc_ISO_plus00:00\",\"calendar_source_sha256\":\"174a032efce4082b8661eabe84b0cf6094048e937722bdf1659c8cb6c7decb89\",\"daily_time_policy\":\"DailyPreciseEndTime_true_Time_open_EndTime_close_Period_close_minus_open\",\"first_session\":\"2020-12-31\",\"full_axis_count\":3466,\"full_binding_count\":6151,\"history\":\"one_fixed_typed_TradeBar_Daily_call_per_selected_original_symbol_RAW_noFF_regular_hours\",\"last_session\":\"2026-10-13\",\"maximum_history_calls\":5,\"ordered_full_axis_sha256\":\"4ac84a2d01e18691a152812851857195ef56dac16b82ceb72bcf7dd068f86585\",\"own_universe_tickers\":[\"SPY\",\"QQQ\",\"SOXX\",\"XLV\",\"REMX\",\"XLE\",\"XLI\",\"XLF\"],\"package_sha256\":\"1ab48d0b9c87710b05e109f234795a6bfbf5ea1b756664f8b58305dcb41173f2\",\"requested_session_count\":1452,\"schema\":\"arv2-r298-native-price-source-diagnostic-v1-specification\",\"security_master_admission_sha256\":\"5d0075cfe24cdfaaa56992de1d3b30bb4895d2495a8356ade47a4c3bc9dea281\",\"selected_whole_binding_sha256s\":[\"1e241c9aca6d79eef7020990ffa7bca14b8059a72e67bb42a767690ded624331\",\"b0147c90e6741dc9b7697b82cc1d1dc459a0de4445d54c540cdfa7e9319fdce8\",\"b44a76e5db7cedcfc5ddfa6671b6cb28feb306d434d8d3cda3710fb7e3fd61c9\",\"c15d10303e03ea8eb0ce007bed1db63bfc626337dcda2bd94798ef09a5c058f7\",\"f352b4d726b30dc4c0d9ac2b607d4c003dc8ebc4de2fc7442b97b6d8c3f1b986\"],\"source_assignment\":\"exact_five_original_bindings_entire_window_same_all_six_cells_reference_AND_NAV\",\"source_scope\":\"availability_only_no_price_admission_or_Sharadar_refusal_clearance\"}"
_EVIDENCE_JSON = b"{\"original_binding_schema_and_semantic_row_hash_checked_count\":5,\"original_class_and_identity_evidence_checked_count\":5,\"original_native_QC_SIDs_available\":false,\"original_non_USD_functional_reporting_currency_count\":0,\"selected_case_count\":5,\"selected_whole_binding_sha256s\":[\"1e241c9aca6d79eef7020990ffa7bca14b8059a72e67bb42a767690ded624331\",\"b0147c90e6741dc9b7697b82cc1d1dc459a0de4445d54c540cdfa7e9319fdce8\",\"b44a76e5db7cedcfc5ddfa6671b6cb28feb306d434d8d3cda3710fb7e3fd61c9\",\"c15d10303e03ea8eb0ce007bed1db63bfc626337dcda2bd94798ef09a5c058f7\",\"f352b4d726b30dc4c0d9ac2b607d4c003dc8ebc4de2fc7442b97b6d8c3f1b986\"],\"vendor_source_blockers_remaining\":5}"


def observed_fact():
    return json.loads(_FACT_JSON)


def expected_specification():
    return json.loads(_SPEC_JSON)


def expected_selection_evidence():
    return json.loads(_EVIDENCE_JSON)


def profile_record():
    return {'schema': SCHEMA, 'observed_fact_sha256': hashlib.sha256(_FACT_JSON).hexdigest(),
        'specification_sha256': hashlib.sha256(_SPEC_JSON).hexdigest(),
        'selection_evidence_sha256': hashlib.sha256(_EVIDENCE_JSON).hexdigest(),
        'new_QC_source_project_rights_and_run_freeze_required': True,
        'old_control_or_operation_read': False, 'operational_authority_granted': False,
        'paid_rights_granted': False, 'native_identity_admitted': False,
        'strategy_price_admitted': False, 'strategy_nav_admitted': False,
        'point_in_time_proven': False, 'formal_forward_ready': False, 'paper_or_live_ready': False}
