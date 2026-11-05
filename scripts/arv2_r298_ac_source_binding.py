"""Public externally observed AC facts for a separately frozen consumer.

No data/control read or future readiness/permission is provided.
"""
from __future__ import annotations
import hashlib
import json

SCHEMA = 'arv2-r298-ac-price-lineage-source-binding-v1'
_OBSERVED_JSON = b"{\"caller_sha256\":\"2b6de35e7115010573ba40221a85a29174db8004ff35faea5932799b963618d3\",\"expected_head\":\"d25ab8eaaa4a3abea39c41b7e3d6470b429c4e16\",\"private_file\":{\"byte_count\":16344399,\"relative_path\":\"artifacts/analyst_revisions_v2/newrule_price_lineage/R326-20261027-AC/price-lineage-private.json\",\"sha256\":\"4366e1e8a218fb21afc6ef3d88dfed9c2ab8b784a7718a405616850e1a4d6ddc\"},\"producer\":{\"actual_exit\":0,\"bound\":null,\"completion_observed_at\":\"2026-10-27T08:34:26.689193Z\",\"dispatched_at\":\"2026-10-27T08:34:17.171069Z\",\"spawn_observed\":true,\"stderr_bytes\":0,\"stderr_sha256\":\"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855\",\"stdout_bytes\":6063,\"stdout_sha256\":\"1192425eea322cb520cdf7b6af34de384735e53a1e67a26ec1056680ff68b057\"},\"profile_sha256\":\"50a927fc2ce78c79728594a28837c6b8de5d2b152366427e9fba269326a5562b\",\"report\":{\"byte_count\":5934,\"sha256\":\"2eec05418cd5e61ba453c1ee8c900bb5776fd5c21d5e1c05348ca6a701ac4267\"},\"schema\":\"arv2-r298-current-price-acquisition-lineage-ac-v1\",\"validator\":{\"actual_exit\":0,\"bound\":null,\"completion_observed_at\":\"2026-10-27T08:34:30.148700Z\",\"dispatched_at\":\"2026-10-27T08:34:26.689346Z\",\"spawn_observed\":true,\"stderr_bytes\":0,\"stderr_sha256\":\"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855\",\"stdout_bytes\":6063,\"stdout_sha256\":\"1192425eea322cb520cdf7b6af34de384735e53a1e67a26ec1056680ff68b057\"}}"
_SUMMARY_JSON = b"{\"aa_routing_summary_sha256\":\"2f78e37c12d1781f73ecb4d2df6e131b501dfe114f5d5d4169f40f02afd68b22\",\"binding_contract\":{\"admitted_mapping_inventory_sha256\":\"2dedd92e902aa5c0ba88a7ddd40abf75b933fb99fe20b06fd07d7c75156a5359\",\"binding_count\":6151,\"binding_stream_sha256\":\"73ba4ac73c0485b2d274c31b5ec740a97a64de27a4f6dfbfb9cb63bc8e7cd15f\",\"security_master_admission_sha256\":\"5d0075cfe24cdfaaa56992de1d3b30bb4895d2495a8356ade47a4c3bc9dea281\"},\"conditional_never_potential_stock_count\":510,\"current_catalog_unknown_vocabulary_row_count\":67,\"current_display_is_historical_mapping\":false,\"demand_summary_sha256\":\"71043f8d0d0a71e307507e1479675d55ce1bbf25199e650ad8279099854171f0\",\"disposition_counts\":{\"funds\":{\"routed\":8},\"stocks\":{\"conditional_never_potential\":510,\"refused\":5,\"routed\":5636}},\"formal_forward_ready\":false,\"formal_identity_admitted\":false,\"observation_flag_counts\":{\"funds\":{},\"stocks\":{\"current_category_differs\":3,\"current_category_outside_old_common_vocabulary\":2,\"current_exchange_differs\":37,\"current_exchange_outside_old_listing_vocabulary\":9,\"current_mic_differs\":37,\"current_mic_unmapped\":9,\"current_ticker_differs\":26,\"metadata_first_after_window_start\":1371,\"metadata_last_before_window_end\":2121,\"original_reporting_currency_not_usd\":5}},\"old_predicate_only_route_correction_count\":74,\"original_identity_rewritten\":false,\"paper_or_live_ready\":false,\"point_in_time_proven\":false,\"policy_sha256\":\"a820043ee7ec3a42196f012ac20f44af35e54136733f0a93e0a23167bf08dcec\",\"potential_stock_count\":5641,\"price_acquired\":false,\"price_coverage_proven\":false,\"price_input_admitted\":false,\"price_window\":[\"2020-12-31\",\"2026-10-13\"],\"private_frame_byte_count\":16344399,\"private_frame_sha256\":\"4366e1e8a218fb21afc6ef3d88dfed9c2ab8b784a7718a405616850e1a4d6ddc\",\"provider_contact\":false,\"qc_contact\":false,\"refusal_counts\":{\"funds\":{},\"stocks\":{\"global_collision\":1,\"identity_missing\":4}},\"schema\":\"arv2-r298-qualified-price-lineage-routes-v1\",\"scope\":\"qualified_current_vintage_price_locator_observation_not_coverage_admission\",\"source_pins\":{\"aa_frame\":{\"byte_count\":19895631,\"sha256\":\"3776f03b4941d8e6d014dee19f5ee8a05080f214ab7f502d10738f00a689f561\"},\"demand_frame\":{\"byte_count\":4760647,\"sha256\":\"1196778dd1d217c707f5ae0ff3dcd72bcba9b23919e9ffab242ac3226a705201\"},\"funds\":{\"byte_count\":904679,\"sha256\":\"a85d60f8699ae4b606ee11b7a70fd48e683fd8de223f14f5b4e2599434bdefac\"},\"stocks\":{\"byte_count\":2340169,\"sha256\":\"354f578dd11ab0cebe1ff5b6f9ddb596b2d776f4e3161b34b8d4e1723ffe60e6\"}},\"strategy_continued\":false}"


def observed_fact():
    return json.loads(_OBSERVED_JSON)


def expected_summary():
    return json.loads(_SUMMARY_JSON)


def profile_record():
    return {'schema': SCHEMA,
        'observed_fact_sha256': hashlib.sha256(_OBSERVED_JSON).hexdigest(),
        'summary_sha256': hashlib.sha256(_SUMMARY_JSON).hexdigest(),
        'new_consumer_freeze_required': True, 'old_control_or_operation_read': False,
        'source_admission_granted': False, 'operational_authority_granted': False,
        'point_in_time_proven': False, 'strategy_price_admitted': False,
        'strategy_nav_admitted': False, 'formal_forward_ready': False,
        'paper_or_live_ready': False}
