"""Pure source-only R260--R266 reconstruction and genuine October successor.

Historical source descriptors are public provenance, never private-package
capabilities. No historical package is fabricated, loaded or passed to an old
builder; frozen pure source rewrites reconstruct the exact successful bytes.
"""
import ast
import dataclasses
import hashlib
import json
import math
import time
from types import SimpleNamespace

from research.analyst_revisions_v2_qc import accepted_risk_october_order_package as october
from research.analyst_revisions_v2_qc import accepted_risk_six_universe_order_qc_projection as base
from research.analyst_revisions_v2_qc import accepted_risk_six_universe_order_bridge_qc_projection as bridge
from research.analyst_revisions_v2_qc import accepted_risk_six_universe_order_tilt_qc_projection as tilt
from research.analyst_revisions_v2_qc import accepted_risk_six_universe_order_tilt40_qc_projection as forty
from research.analyst_revisions_v2_qc import accepted_risk_six_universe_order_tilt80_qc_projection as eighty
from research.analyst_revisions_v2_qc import accepted_risk_six_universe_order_settlement_qc_projection as settled
from research.analyst_revisions_v2_qc import accepted_risk_six_universe_order_tilt100_qc_projection as hundred
from research.analyst_revisions_v2_qc import accepted_risk_six_universe_order_tilt100_floor_qc_projection as floor
from research.analyst_revisions_v2_qc import accepted_risk_six_universe_order_tilt_ladder_floor_qc_projection as guarded
from research.analyst_revisions_v2_qc import accepted_risk_matched_historical_projection as matched
from research.analyst_revisions_v2_qc import accepted_risk_six_universe_order_relaxed_qc_projection as relaxed
from research.analyst_revisions_v2_qc import six_universe_qcom_exclusion_coverage10_projection as coverage
from research.analyst_revisions_v2_qc import six_universe_qcom_exclusion_three_name_projection as three
from research.analyst_revisions_v2_qc import six_universe_qcom_restored_projection as restored
from research.analyst_revisions_v2_qc import six_universe_qcom_restored_score_floor1_projection as score_one

SCHEMA = 'arv2-r343-legacy-six-october-projection-v1'
AR_PERCENTS = (80, 100, 120, 140, 160, 180, 200)
EPOCH = 'R343-legacy-six-QCOM-restored-through-2026Oct13-v1'
ORDER = 'accepted_risk_six_universe_order_qc_runtime.py'
BRIDGE = 'accepted_risk_six_universe_order_bridge_qc_runtime.py'
TARGET = 'accepted_risk_six_universe_order_tilt_targets.py'
TILT = 'accepted_risk_six_universe_order_tilt_qc_runtime.py'
OLD_ACTIVATION = {'object_store_key': 'arv2/preliminary-rating/73643a2cc47b5ed07cd79498/transport-manifest.json',
    'content_sha256': '69b663c35b245e965b2d4e1f8402b3b14432d6d713f387eacb888f6756e78a41', 'byte_count': 4015}
OLD_PACKAGE = '7803b84f0841f9685a4951de58fbccf82f3f647cef7beffce31cb4865ea14e1f'
OCTOBER_PACKAGE = '411c2734da61c7d4172c4cb3d33c4ffdde650f40336a5e807d26e50cc7de0bad'
OCTOBER_LINEAGE = 'e4518e06a68a18a3151fe36e5926699624fc68b97c31a8e06917d44103831fd9'
FALSE_FLAGS = {key: False for key in ('point_in_time_proven', 'formal_identity_admitted',
    'formal_forward_ready', 'source_admission_granted', 'backtest_completed', 'paper_or_live_ready',
    'QC_contact', 'provider_contact', 'historical_package_loaded', 'frozen_module_globals_modified')}
FINITE = frozenset(('input', 'bindings', 'source_pin', 'historical', 'transform', 'period', 'profile',
    'source_audit', 'bound', 'output', 'deadline', 'unknown'))
MAX_SECONDS = 600
REPORTING_SOURCE_PIN = {'byte_count': 18635, 'sha256': '0a61059da3539ba30a8ca7d917484d47a7305676e873f7c85bb27f82ff5a615c'}
HISTORICAL_MANIFEST = {'activation_manifest_sha256': '69b663c35b245e965b2d4e1f8402b3b14432d6d713f387eacb888f6756e78a41', 'candidates': [{'analyst_revision_economic_usage': 'entry_count_and_weight', 'arm': 'ar_on80', 'backtest_name': 'ARV2 R260 QCOM score floor1 AR80 2021 2025', 'candidate_id': 'R260', 'coverage_policy_id': 'all_six_minimum_mapping_cap_total_10pct_verified_names_3_positive_scores_1_v1', 'kind': 'order', 'matched_baseline_profile_sha256': 'a2e882373cd9aa288dafbe9072e9e02e6ac042599d8da8ec931e055e4c4beb04', 'meta_schema': 'arv2-six-matched-qcom-admitted-r260-score-floor1-three-name-ar_on80-meta-v1', 'minimum_positive_score_count': 1, 'minimum_verified_name_count': 3, 'profile_id': 'arv2-six-matched-qcom-admitted-r260-score-floor1-three-name-ar_on80-s0-profile-v1', 'profile_sha256': 'a2b0ba1383dac6606942cd4416481da88b9734a19eef334643c22f3867f8e091', 'project_name': 'ARV2 SIX QCOM FLOOR1 R260 AR80 2021 2025', 'projection_schema': 'arv2-six-qcom-admitted-r260-score-floor1-projection-v1', 'projection_sha256': 'e12f5d60b77cec2a18f5c68b5cbc4c6a900c819c14aea462ca8b440350f2b801', 'reference_repair_enabled': True, 'role': 'matched_qcom_admitted_r260_score_floor1_three_name_ar_on80_s0', 'slippage_bps': 0, 'source_candidate_id': 'R256', 'source_file_count': 17, 'source_files_sha256': '6413f8b50fdee82292fa69bfdaf97e7bf2b979865aa9a9da9e95656544786176', 'source_manifest_sha256': '032d513c197507146c793bced6cfb5085347727c8558fc96bb91aeaa06473e62', 'source_profile_sha256': 'b07e9241187c243cd202c4e0b6e193396248d5edea04910285910d82ba1b6313', 'source_projection_sha256': '7f53404c5bad44996dde2c2cec7d8fb30983f63384d431d0e6c005058288e924', 'statistic_names': ['ARV2_SIX_GATE_ORDER_META', 'ARV2_SIX_GATE_ORDER_AGGREGATES', 'ARV2_SIX_GATE_ORDER_DIAGNOSTICS'], 'summary_schema': 'arv2-six-matched-qcom-admitted-r260-score-floor1-three-name-ar_on80-summary-v1', 'tilt_fraction': '0.80', 'total_source_bytes': 404451}, {'analyst_revision_economic_usage': 'entry_count_and_weight', 'arm': 'ar_on100', 'backtest_name': 'ARV2 R261 QCOM score floor1 AR100 2021 2025', 'candidate_id': 'R261', 'coverage_policy_id': 'all_six_minimum_mapping_cap_total_10pct_verified_names_3_positive_scores_1_v1', 'kind': 'order', 'matched_baseline_profile_sha256': '3493579b53c1253940a17a2b67c2cf666c78b050929ef93d1b863390309cbf6b', 'meta_schema': 'arv2-six-matched-qcom-admitted-r261-score-floor1-three-name-ar_on100-meta-v1', 'minimum_positive_score_count': 1, 'minimum_verified_name_count': 3, 'profile_id': 'arv2-six-matched-qcom-admitted-r261-score-floor1-three-name-ar_on100-s0-profile-v1', 'profile_sha256': 'b799f2d62f1fa0f2a37a880376379667dfced6f0232bc0a35655f5cc592ddeee', 'project_name': 'ARV2 SIX QCOM FLOOR1 R261 AR100 2021 2025', 'projection_schema': 'arv2-six-qcom-admitted-r261-score-floor1-projection-v1', 'projection_sha256': '932b76962609ae8ee17b55f7ce90ea3a30d75d5d949cc68127f88731faba7fb2', 'reference_repair_enabled': True, 'role': 'matched_qcom_admitted_r261_score_floor1_three_name_ar_on100_s0', 'slippage_bps': 0, 'source_candidate_id': 'R256', 'source_file_count': 17, 'source_files_sha256': 'e8d5d8932a4e6edb636c5bfdbded5d7dd4f8964a8688cf71d8cd5d34417def3b', 'source_manifest_sha256': '032d513c197507146c793bced6cfb5085347727c8558fc96bb91aeaa06473e62', 'source_profile_sha256': 'b07e9241187c243cd202c4e0b6e193396248d5edea04910285910d82ba1b6313', 'source_projection_sha256': '7f53404c5bad44996dde2c2cec7d8fb30983f63384d431d0e6c005058288e924', 'statistic_names': ['ARV2_SIX_GATE_ORDER_META', 'ARV2_SIX_GATE_ORDER_AGGREGATES', 'ARV2_SIX_GATE_ORDER_DIAGNOSTICS'], 'summary_schema': 'arv2-six-matched-qcom-admitted-r261-score-floor1-three-name-ar_on100-summary-v1', 'tilt_fraction': '1.00', 'total_source_bytes': 404471}, {'analyst_revision_economic_usage': 'entry_count_and_weight', 'arm': 'ar_on120', 'backtest_name': 'ARV2 R262 QCOM score floor1 AR120 2021 2025', 'candidate_id': 'R262', 'coverage_policy_id': 'all_six_minimum_mapping_cap_total_10pct_verified_names_3_positive_scores_1_v1', 'kind': 'order', 'matched_baseline_profile_sha256': '43ebf68dc7986b446faa0b41e4f74cd7fb155e5721cd312e2098e00f01241b5a', 'meta_schema': 'arv2-six-matched-qcom-admitted-r262-score-floor1-three-name-ar_on120-meta-v1', 'minimum_positive_score_count': 1, 'minimum_verified_name_count': 3, 'profile_id': 'arv2-six-matched-qcom-admitted-r262-score-floor1-three-name-ar_on120-s0-profile-v1', 'profile_sha256': 'c3082e51c86d3d96d191f06a5c2eb9bf112fd06e283da70793d3996ca5f9625a', 'project_name': 'ARV2 SIX QCOM FLOOR1 R262 AR120 2021 2025', 'projection_schema': 'arv2-six-qcom-admitted-r262-score-floor1-projection-v1', 'projection_sha256': '8dd192073cc4772170982904214154a2ddba3ca73763a269fafdd41b119e36b3', 'reference_repair_enabled': True, 'role': 'matched_qcom_admitted_r262_score_floor1_three_name_ar_on120_s0', 'slippage_bps': 0, 'source_candidate_id': 'R257', 'source_file_count': 17, 'source_files_sha256': '235e2af8f85806f744651559f78dcb29c53a50858763dd4dd68ff2e7942134a7', 'source_manifest_sha256': '032d513c197507146c793bced6cfb5085347727c8558fc96bb91aeaa06473e62', 'source_profile_sha256': 'e380009fb6966d9acd1b9883e9d7619163faf2c859caed56d0b58d5349af7a7c', 'source_projection_sha256': '6fec1642589062cc6810250fda9d8be70f83bd7c4c5f771d65a8e480de0d99a3', 'statistic_names': ['ARV2_SIX_GATE_ORDER_META', 'ARV2_SIX_GATE_ORDER_AGGREGATES', 'ARV2_SIX_GATE_ORDER_DIAGNOSTICS'], 'summary_schema': 'arv2-six-matched-qcom-admitted-r262-score-floor1-three-name-ar_on120-summary-v1', 'tilt_fraction': '1.20', 'total_source_bytes': 404471}, {'analyst_revision_economic_usage': 'entry_count_and_weight', 'arm': 'ar_on140', 'backtest_name': 'ARV2 R263 QCOM score floor1 AR140 2021 2025', 'candidate_id': 'R263', 'coverage_policy_id': 'all_six_minimum_mapping_cap_total_10pct_verified_names_3_positive_scores_1_v1', 'kind': 'order', 'matched_baseline_profile_sha256': 'cdad9eee4924e95711720dbde62bd4722c8071adcf8f51d73e45f2287b382b0e', 'meta_schema': 'arv2-six-matched-qcom-admitted-r263-score-floor1-three-name-ar_on140-meta-v1', 'minimum_positive_score_count': 1, 'minimum_verified_name_count': 3, 'profile_id': 'arv2-six-matched-qcom-admitted-r263-score-floor1-three-name-ar_on140-s0-profile-v1', 'profile_sha256': '50b841a4609ceaf727dde3f296e424f7c8d29cdbda9338ae924692aa08c6f489', 'project_name': 'ARV2 SIX QCOM FLOOR1 R263 AR140 2021 2025', 'projection_schema': 'arv2-six-qcom-admitted-r263-score-floor1-projection-v1', 'projection_sha256': 'a2e05e106752d6f429795010ad6635b25969756f03e9433303a801ef7b59b990', 'reference_repair_enabled': True, 'role': 'matched_qcom_admitted_r263_score_floor1_three_name_ar_on140_s0', 'slippage_bps': 0, 'source_candidate_id': 'R256', 'source_file_count': 17, 'source_files_sha256': '57584f0b507db1542ebdea8df0197ec5051cf1e79d0e0ae23b41adb361dfde84', 'source_manifest_sha256': '032d513c197507146c793bced6cfb5085347727c8558fc96bb91aeaa06473e62', 'source_profile_sha256': 'b07e9241187c243cd202c4e0b6e193396248d5edea04910285910d82ba1b6313', 'source_projection_sha256': '7f53404c5bad44996dde2c2cec7d8fb30983f63384d431d0e6c005058288e924', 'statistic_names': ['ARV2_SIX_GATE_ORDER_META', 'ARV2_SIX_GATE_ORDER_AGGREGATES', 'ARV2_SIX_GATE_ORDER_DIAGNOSTICS'], 'summary_schema': 'arv2-six-matched-qcom-admitted-r263-score-floor1-three-name-ar_on140-summary-v1', 'tilt_fraction': '1.40', 'total_source_bytes': 404471}, {'analyst_revision_economic_usage': 'entry_count_and_weight', 'arm': 'ar_on160', 'backtest_name': 'ARV2 R264 QCOM score floor1 AR160 2021 2025', 'candidate_id': 'R264', 'coverage_policy_id': 'all_six_minimum_mapping_cap_total_10pct_verified_names_3_positive_scores_1_v1', 'kind': 'order', 'matched_baseline_profile_sha256': 'b65005be122d9bfc6ccb3a6d61d2ba0ec7abe9c2b35892be1e945dfa236aa90b', 'meta_schema': 'arv2-six-matched-qcom-admitted-r264-score-floor1-three-name-ar_on160-meta-v1', 'minimum_positive_score_count': 1, 'minimum_verified_name_count': 3, 'profile_id': 'arv2-six-matched-qcom-admitted-r264-score-floor1-three-name-ar_on160-s0-profile-v1', 'profile_sha256': 'd264d51bb5c3900cfb283cd043caf319587c303c1b139674b3aa4c0deb5a7a66', 'project_name': 'ARV2 SIX QCOM FLOOR1 R264 AR160 2021 2025', 'projection_schema': 'arv2-six-qcom-admitted-r264-score-floor1-projection-v1', 'projection_sha256': 'a0ce043a5fa34d228f1fa628885e69617e06852d910c503de6df487ecbe0a072', 'reference_repair_enabled': True, 'role': 'matched_qcom_admitted_r264_score_floor1_three_name_ar_on160_s0', 'slippage_bps': 0, 'source_candidate_id': 'R256', 'source_file_count': 17, 'source_files_sha256': 'a9639e1bad64fa843eabb63ceed36f37d8c92fa68b048de9838a237e959ae6c0', 'source_manifest_sha256': '032d513c197507146c793bced6cfb5085347727c8558fc96bb91aeaa06473e62', 'source_profile_sha256': 'b07e9241187c243cd202c4e0b6e193396248d5edea04910285910d82ba1b6313', 'source_projection_sha256': '7f53404c5bad44996dde2c2cec7d8fb30983f63384d431d0e6c005058288e924', 'statistic_names': ['ARV2_SIX_GATE_ORDER_META', 'ARV2_SIX_GATE_ORDER_AGGREGATES', 'ARV2_SIX_GATE_ORDER_DIAGNOSTICS'], 'summary_schema': 'arv2-six-matched-qcom-admitted-r264-score-floor1-three-name-ar_on160-summary-v1', 'tilt_fraction': '1.60', 'total_source_bytes': 404471}, {'analyst_revision_economic_usage': 'entry_count_and_weight', 'arm': 'ar_on180', 'backtest_name': 'ARV2 R265 QCOM score floor1 AR180 2021 2025', 'candidate_id': 'R265', 'coverage_policy_id': 'all_six_minimum_mapping_cap_total_10pct_verified_names_3_positive_scores_1_v1', 'kind': 'order', 'matched_baseline_profile_sha256': '1a1d396caf927baab992e3a71d1fdea79433c8d2d80e5eebe1f7347e54ff500b', 'meta_schema': 'arv2-six-matched-qcom-admitted-r265-score-floor1-three-name-ar_on180-meta-v1', 'minimum_positive_score_count': 1, 'minimum_verified_name_count': 3, 'profile_id': 'arv2-six-matched-qcom-admitted-r265-score-floor1-three-name-ar_on180-s0-profile-v1', 'profile_sha256': 'e63aa7a2f029c491bef2acf8f7f58b039413f595835772496bad1217424215e2', 'project_name': 'ARV2 SIX QCOM FLOOR1 R265 AR180 2021 2025', 'projection_schema': 'arv2-six-qcom-admitted-r265-score-floor1-projection-v1', 'projection_sha256': '965e8ce9a85ca4525831b9e1c5177f2fe43e1f200b953bc0b1715acfae55d2dd', 'reference_repair_enabled': True, 'role': 'matched_qcom_admitted_r265_score_floor1_three_name_ar_on180_s0', 'slippage_bps': 0, 'source_candidate_id': 'R256', 'source_file_count': 17, 'source_files_sha256': '35a528a686c0be261201394d00165515706390a867135dbb20e99fe12269192e', 'source_manifest_sha256': '032d513c197507146c793bced6cfb5085347727c8558fc96bb91aeaa06473e62', 'source_profile_sha256': 'b07e9241187c243cd202c4e0b6e193396248d5edea04910285910d82ba1b6313', 'source_projection_sha256': '7f53404c5bad44996dde2c2cec7d8fb30983f63384d431d0e6c005058288e924', 'statistic_names': ['ARV2_SIX_GATE_ORDER_META', 'ARV2_SIX_GATE_ORDER_AGGREGATES', 'ARV2_SIX_GATE_ORDER_DIAGNOSTICS'], 'summary_schema': 'arv2-six-matched-qcom-admitted-r265-score-floor1-three-name-ar_on180-summary-v1', 'tilt_fraction': '1.80', 'total_source_bytes': 404471}, {'analyst_revision_economic_usage': 'entry_count_and_weight', 'arm': 'ar_on200', 'backtest_name': 'ARV2 R266 QCOM score floor1 AR200 2021 2025', 'candidate_id': 'R266', 'coverage_policy_id': 'all_six_minimum_mapping_cap_total_10pct_verified_names_3_positive_scores_1_v1', 'kind': 'order', 'matched_baseline_profile_sha256': 'a8c1308d32e509182a4d2b7ce47bd1f4689b50046e2e884d97a3086de48c3d34', 'meta_schema': 'arv2-six-matched-qcom-admitted-r266-score-floor1-three-name-ar_on200-meta-v1', 'minimum_positive_score_count': 1, 'minimum_verified_name_count': 3, 'profile_id': 'arv2-six-matched-qcom-admitted-r266-score-floor1-three-name-ar_on200-s0-profile-v1', 'profile_sha256': 'd1ae705e3bbc37dc71ae97ccb2661cc617aed6d50c7156a643a2a2ff9f41e7bd', 'project_name': 'ARV2 SIX QCOM FLOOR1 R266 AR200 2021 2025', 'projection_schema': 'arv2-six-qcom-admitted-r266-score-floor1-projection-v1', 'projection_sha256': '6e0cf5b25f845ae85dedb509f47e31197c86cbc4c5f453b033f96c106133cdb0', 'reference_repair_enabled': True, 'role': 'matched_qcom_admitted_r266_score_floor1_three_name_ar_on200_s0', 'slippage_bps': 0, 'source_candidate_id': 'R258', 'source_file_count': 17, 'source_files_sha256': '01c74064dd1ef2e7dbcb517d9a69d5073dbd3d0e9022b4b19fff848ec678f84d', 'source_manifest_sha256': '032d513c197507146c793bced6cfb5085347727c8558fc96bb91aeaa06473e62', 'source_profile_sha256': 'cb66fe9a4f0b1cc3fed0f0af7842dd45280ff44a1a82e9f8ea8d1d988da35c69', 'source_projection_sha256': 'ae6ee5ee842e9b39c41d8f07fbd44377fb28fa05143c8bf652ee60021fd7df60', 'statistic_names': ['ARV2_SIX_GATE_ORDER_META', 'ARV2_SIX_GATE_ORDER_AGGREGATES', 'ARV2_SIX_GATE_ORDER_DIAGNOSTICS'], 'summary_schema': 'arv2-six-matched-qcom-admitted-r266-score-floor1-three-name-ar_on200-summary-v1', 'tilt_fraction': '2.00', 'total_source_bytes': 404471}], 'package_sha256': '7803b84f0841f9685a4951de58fbccf82f3f647cef7beffce31cb4865ea14e1f', 'protocol': {'admission_leverage': '2', 'candidate_ids': ['R260', 'R261', 'R262', 'R263', 'R264', 'R265', 'R266'], 'confirmation': False, 'cost_bps_per_side': '10', 'decision_count': 261, 'floor3_reference_candidate_id': 'R257', 'floor3_reference_remx_post_cap_stock_target_count': 0, 'floor3_reference_total_post_cap_stock_target_count': 12211, 'formal_alpha': False, 'historical_order_window': ['2021-01-04', '2025-12-31'], 'maximum_attempts_per_candidate': 3, 'minimum_positive_score_count': 1, 'minimum_verified_name_count': 3, 'observation_count': 1255, 'one_change': 'QCOM_admitted_three_name_positive_score_floor_3_to_1_and_versioned_tilt_ladder', 'paper_live_trading': False, 'physical_orders': True, 'pilot_candidate_id': 'R261', 'pilot_required_remx_post_cap_stock_target_count_at_least': 1, 'pilot_required_total_post_cap_stock_target_count_above': 12211, 'sensitivity_only': True, 'slippage_bps': 0, 'source_ids': ['R256', 'R256', 'R257', 'R256', 'R256', 'R256', 'R258'], 'target_gross_exposure': '0.98'}, 'schema': 'arv2-six-qcom-admitted-score-floor1-tilt-ladder-v1'}
HOST_SOURCE_PINS = {'accepted_risk_matched_diagnostics.py': 'e09487a99b6fdc7f999056b9df438f0c65ebb52083c6cbe6ce29130614dacacd', 'accepted_risk_order_level_core.py': '063ed8fb7024c879a640780c07723c7edfb95665acc711d02fc8be0d964e965f', 'accepted_risk_order_level_forced_exit.py': '21ef6978d7c26b833b0ec553298584c360f03d602f3c244f2fc8645bd113ec3f', 'accepted_risk_order_level_input_runtime.py': 'a08098648d98a95736471113d48a3e1183f04969d2c2561b1a4f5d6bfc80d7ee', 'accepted_risk_preliminary_qc_figi.py': '4ee85d92126e31d3bde9acaffb992a54cf44b02efa876157597b876086da7ca9', 'accepted_risk_preliminary_rating_evaluator.py': '2fb9bc8a8f74e37b57acb97f4d20b5820be04b9ee470fc2f34b3a8ea2c804910', 'accepted_risk_preliminary_rating_policy.py': '7d45e0c294d03b5775ca6bd911043ea1e9b819e448eb7107fcbf0a2f162e36bd', 'accepted_risk_sequential_r055_score.py': '6c34940cb821c04554e9073a77e013d306d059a688dbac02fe5b0511d91d217b', 'accepted_risk_simulated_moo_executor.py': 'e2f4b5508427e6f4c5bf20813e255cecae1d8652177391eeb226dc56084c5fb7', 'accepted_risk_six_universe_gate.py': '158445ae072ef6c66a49b2069c53b02ee805adbccbb9a522650ccd3a72fa9f1e', 'accepted_risk_six_universe_gate_evaluator.py': 'd0f1ba677c63f2caf3703cd7a4df5fbc8ef6225aac4a2357c7d54003da73eb1c', 'accepted_risk_six_universe_order_bridge_qc_runtime.py': '60b0e300393c1356e21de310fdfce1ff029632d77e6bf62efd7bb053de55b5ab', 'accepted_risk_six_universe_order_qc_runtime.py': '84e4d69135ff13f592e071574d22b30255088f4df22bd11f33943c652d81a46a', 'accepted_risk_six_universe_order_targets.py': '0b280fdc1ebcb5f8ab073ff78f3008057e86db14b6254145bc5f86e18d2e5ea0', 'accepted_risk_six_universe_order_tilt_qc_runtime.py': 'd6cd9f963e4754e134d1a6116ee300711ad7e28bc0e4b95f15e241d7e22f1489', 'accepted_risk_six_universe_order_tilt_targets.py': 'b063c5bca9e4aa13e2deff66726cc4b6c12c405845921c1ee39bbe653f266506'}


class Refused(ValueError):
    """Closed finite predicate only."""


def finite(error):
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def require(value, code):
    if not value: raise Refused(code)


def budget(deadline):
    require(type(deadline) in (int, float) and math.isfinite(deadline)
        and 0 < deadline - time.monotonic() <= MAX_SECONDS, 'deadline')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
        allow_nan=False).encode('ascii')


def sha(raw): return hashlib.sha256(raw).hexdigest()
def pin(raw): return {'byte_count': len(raw), 'sha256': sha(raw)}


def source_names():
    return tuple(sorted(set(base._SOURCE_PATHS) | {BRIDGE, TARGET, TILT, matched.DIAGNOSTICS_PATH}))


def _literal_transforms(sources, module, transforms):
    return {name: module._replace_exact(raw.encode('ascii'), transforms[name]).decode('ascii')
        if name in transforms else raw for name, raw in sources.items()}


def _profile(sources, *, old_baseline=None):
    with relaxed._cloud_loader(sources) as (load, _):
        baseline = load(relaxed._BRIDGE_NAME).require_bridge_profile('matched')
        if old_baseline is not None:
            sources[TILT] = relaxed._replace(sources[TILT], old_baseline, baseline['profile_sha256'])
        runtime = load(TILT[:-3]); result = runtime.require_tilt_profile()
        runtime.expected_tilt_custom_statistic_names()
        return result, SimpleNamespace(role=result['role'], variant=runtime.TILT_VARIANT,
            profile_id=result['profile_id'], profile_sha256=result['profile_sha256'])


def reconstruct_historical(source_pairs, *, qcom_security_id, manifest, deadline):
    """Return exact successful cloud buffers; no old private wrapper or operator."""
    budget(deadline)
    require(type(source_pairs) is tuple and len(source_pairs) == len(source_names()), 'source_pin')
    supplied = dict(source_pairs)
    require(len(supplied) == len(source_pairs) and set(supplied) == set(source_names())
        and all(type(raw) is bytes and raw.isascii() and 0 < len(raw) <= 131072 for raw in supplied.values()), 'source_pin')
    require(all(sha(supplied[name]) == HOST_SOURCE_PINS[name] for name in supplied), 'source_pin')
    require(type(qcom_security_id) is str and sha(qcom_security_id.encode('utf8'))
        == matched.QCOM_EXCLUSION_SECURITY_ID_SHA256, 'bindings')
    require(type(manifest) is dict and sha(canonical(manifest))
        == 'a3f148b3833137adffc5a779cf2b60e0151a4ef20297a139f5a851b60f71ab06', 'historical')
    # The original public Main descriptor is not an input-package authority.
    activation = SimpleNamespace(**OLD_ACTIVATION)
    sources = {name: supplied[name].decode('ascii') for name in base._SOURCE_PATHS}
    sources[ORDER] = base._cap90_qc_runtime_source(supplied[ORDER]).decode('ascii')
    sources[BRIDGE] = supplied[BRIDGE].decode('ascii')
    for name in (TARGET, TILT): sources[name] = supplied[name].decode('ascii')
    sources['main.py'] = tilt._tilt_main_source(activation, tilt._tilt_runtime.require_tilt_profile()).decode('ascii')
    sources = _literal_transforms(sources, forty, forty._TRANSFORMS)
    sources = _literal_transforms(sources, eighty, eighty._TRANSFORMS)
    for name, raw in tuple(sources.items()):
        if name == 'accepted_risk_order_level_core.py': raw = settled._core_source(raw)
        elif name == BRIDGE: raw = settled._bridge_source(raw)
        elif name == TILT: raw = settled._tilt_source(raw, settled.require_settlement_profile('R191')['profile_sha256'])
        elif name == 'main.py': raw = settled._replace_exact(raw,
            f"variant='{eighty.TILT80_VARIANT}',", f"variant='{settled.TILT_VARIANT}',")
        sources[name] = raw
    sources = _literal_transforms(sources, hundred, hundred._TRANSFORMS)
    sources = _literal_transforms(sources, floor, floor._TRANSFORMS)
    sources = _literal_transforms(sources, guarded, guarded._transforms(100))
    for name, original in tuple(sources.items()):
        raw = relaxed._render_source(name, original, 100, relaxed._selection.ALL25_COVERAGE_POLICY, all25=True)
        if name == 'accepted_risk_order_level_input_runtime.py': raw = matched._recent._correct_input_reader(original)
        sources[name] = matched._render_fee_basis(name, matched._render_reference_refusal(name,
            matched._render_diagnostics(name, matched._render_identity(name, raw, 'ar_on100', 0), 'ar_on100', 0)))
    sources[matched.DIAGNOSTICS_PATH] = supplied[matched.DIAGNOSTICS_PATH].decode('ascii')
    prior, _ = _profile(sources, old_baseline=settled.CANDIDATES['R191']['profile_sha256'])
    sources = {name: matched._render_qcom_exclusion(name, raw, qcom_security_id, 'ar_on100', 0)
        for name, raw in sources.items()}
    prior, _ = _profile(sources, old_baseline=prior['matched_baseline_profile_sha256'])
    common = sources
    cells = []
    for percent, historical in zip(AR_PERCENTS, manifest['candidates'], strict=True):
        budget(deadline)
        old_percent = 120 if percent == 120 else 200 if percent == 200 else 80
        sources = {name: matched._render_qcom_exclusion_tilt(name, raw, old_percent)
            for name, raw in common.items()}
        profile, descriptor = _profile(sources)
        arm = f'ar_on{old_percent}'
        sources = {name: coverage._render_source(name, raw, descriptor, profile, arm) for name, raw in sources.items()}
        profile, descriptor = _profile(sources, old_baseline=profile['matched_baseline_profile_sha256'])
        sources = {name: three._render_source(name, raw, descriptor, arm) for name, raw in sources.items()}
        profile, descriptor = _profile(sources, old_baseline=profile['matched_baseline_profile_sha256'])
        old_id = {80: 'R256', 120: 'R257', 200: 'R258'}[old_percent]
        sources = {name: restored.render_qcom_admitted_source(name, raw,
            security_id=qcom_security_id, new_candidate_id=old_id) for name, raw in sources.items()}
        profile, descriptor = _profile(sources, old_baseline=profile['matched_baseline_profile_sha256'])
        sources = {name: score_one._render_source(name, raw, old_id=old_id,
            old_percent=old_percent, percent=percent, new_id=historical['candidate_id']) for name, raw in sources.items()}
        profile, descriptor = _profile(sources, old_baseline=profile['matched_baseline_profile_sha256'])
        buffers = tuple(sorted((name, raw.encode('ascii')) for name, raw in sources.items()))
        records = tuple((name, sha(raw), len(raw)) for name, raw in buffers)
        require(len(buffers) == 17 and profile['profile_sha256'] == historical['profile_sha256']
            and sha(canonical(records)) == historical['source_files_sha256']
            and sum(len(raw) for _, raw in buffers) == historical['total_source_bytes'], 'historical')
        for name, raw in buffers: base._audit_source(name, raw)
        cells.append((percent, buffers, profile))
    return tuple(cells)


def _period_source(name, raw, *, percent, old_id, activation):
    """Declared date/count/identity and terminal-clock delta; financial AST intact."""
    tree = ast.parse(raw)
    period_names = {ORDER, BRIDGE, 'accepted_risk_six_universe_gate_evaluator.py', matched.DIAGNOSTICS_PATH}
    old_slug, new_slug = old_id.lower(), f'r343_ar{percent:03d}_legacy_october'
    class Period(ast.NodeTransformer):
        def visit_Constant(self, node):
            value = node.value
            if type(value) is str:
                value = value.replace(f'qcom_admitted_{old_slug}', f'qcom_admitted_{new_slug}')
                value = value.replace(f'qcom-admitted-{old_slug}', f'qcom-admitted-{new_slug}')
                value = value.replace(f'QCOM-admitted-{old_id}', f'QCOM-admitted-R343-AR{percent:03d}')
                if name in period_names:
                    value = value.replace('2025-12-31', '2026-10-13').replace('2025-12-29', '2026-10-12')
                    value = value.replace('2026-01-01_00:00', '2026-10-14_00:00')
                if name == 'main.py':
                    if value == OLD_ACTIVATION['object_store_key']: value = activation['object_store_key']
                    elif value == OLD_ACTIVATION['content_sha256']: value = activation['content_sha256']
                node.value = value
            elif type(value) is int:
                if name in period_names and value in (261, 1255, 1254):
                    node.value = {261: 302, 1255: 1451, 1254: 1450}[value]
                if name == matched.DIAGNOSTICS_PATH and value == 7530:
                    node.value = 8706
                if name == 'main.py' and value == OLD_ACTIVATION['byte_count']:
                    node.value = activation['byte_count']
            return node
        def visit_ClassDef(self, node):
            node.name = node.name.replace(f'QcomAdmitted{old_id}', f'R343LegacySixAr{percent:03d}')
            return self.generic_visit(node)
        def visit_Compare(self, node):
            # Both genuine old terminal consumers demand the next midnight.
            if (name in (ORDER, BRIDGE) and len(node.comparators) == 1 and isinstance(node.left, ast.Attribute)
                    and isinstance(node.left.value, ast.Name) and node.left.value.id == 'end_clock'):
                field = node.left.attr
                if field in ('month', 'day'):
                    require(isinstance(node.comparators[0], ast.Constant) and node.comparators[0].value == 1, 'transform')
                    node.comparators[0] = ast.Constant(10 if field == 'month' else 14)
            if (name == matched.DIAGNOSTICS_PATH and len(node.comparators) == 1
                    and isinstance(node.left, ast.Call) and isinstance(node.left.func, ast.Name)
                    and node.left.func.id == 'len' and len(node.left.args) == 1
                    and isinstance(node.left.args[0], ast.Name)):
                count_name = node.left.args[0].id
                if count_name in ('annual', 'rows') and isinstance(node.comparators[0], ast.Constant):
                    value = node.comparators[0].value
                    if (count_name, value) in (('annual', 5), ('rows', 30)):
                        node.comparators[0] = ast.Constant(6 if count_name == 'annual' else 36)
            return self.generic_visit(node)
        def visit_Call(self, node):
            if name == 'main.py' and isinstance(node.func, ast.Attribute) and node.func.attr == 'set_end_date':
                require([n.value for n in node.args] == [2025, 12, 31], 'transform')
                node.args = [ast.Constant(n) for n in (2026, 10, 13)]
            if name == matched.DIAGNOSTICS_PATH and isinstance(node.func, ast.Name) and node.func.id == 'range':
                if [ast.literal_eval(n) for n in node.args] == [2021, 2026]: node.args[-1] = ast.Constant(2027)
            return self.generic_visit(node)
    try:
        result = Period().visit(tree)
        ast.fix_missing_locations(result)
        rendered = (ast.unparse(result) + '\n').encode('ascii')
        require(ast.dump(ast.parse(rendered), include_attributes=False) == ast.dump(result, include_attributes=False), 'transform')
        return rendered
    except Refused: raise
    except (ValueError, TypeError, SyntaxError, UnicodeError): raise Refused('transform') from None


def _extend_cell(percent, original_sources, original_profile, *, activation, reporting_source):
    old_id = HISTORICAL_MANIFEST['candidates'][AR_PERCENTS.index(percent)]['candidate_id']
    sources = {name: _period_source(name, raw, percent=percent, old_id=old_id, activation=activation).decode('ascii')
        for name, raw in original_sources}
    # Derive the genuine changed bridge/profile chain before binding the tilt.
    profile, _ = _profile(sources, old_baseline=original_profile['matched_baseline_profile_sha256'])
    tree = ast.parse(sources[TILT])
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'require_tilt_profile')
    seeds = [n for n in ast.walk(function) if isinstance(n, ast.Assign)
        and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) and n.targets[0].id == 'seed']
    require(len(seeds) == 1, 'transform')
    index = function.body.index(seeds[0]) + 1
    function.body.insert(index, ast.parse('seed.update(' + repr({'research_epoch_id': EPOCH,
        'source_package_sha256': OCTOBER_PACKAGE, 'source_lineage_sha256': OCTOBER_LINEAGE,
        'original_profile_sha256': original_profile['profile_sha256'],
        'candidate_id': f'R343-AR{percent:03d}'}) + ')').body[0])
    sources[TILT] = ast.unparse(ast.fix_missing_locations(tree)) + '\n'
    profile, _ = _profile(sources)
    sources['legacy_six_october_reporting.py'] = reporting_source.decode('ascii')
    # The report consumes the actual returned aggregate after all unchanged
    # bridge/tilt safety checks and emission, never a second aggregate call.
    tree = ast.parse(sources['main.py'])
    base_imports = [node for node in tree.body if isinstance(node, ast.ImportFrom)
        and node.module == ORDER[:-3]]
    require(len(base_imports) == 1 and all(alias.name != 'ACCOUNT_PATH_SCHEMA' for alias in base_imports[0].names), 'transform')
    base_imports[0].names.append(ast.alias('ACCOUNT_PATH_SCHEMA'))
    tree.body.insert(1, ast.ImportFrom('legacy_six_october_reporting',
        [ast.alias('build_report'), ast.alias('canonical_report_bytes'), ast.alias('STATISTIC_NAME')], 0))
    end = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'on_end_of_algorithm']
    require(len(end) == 1 and len(end[0].body) == 1 and isinstance(end[0].body[0], ast.Expr)
        and ast.unparse(end[0].body[0]) == 'self._arv2_driver.on_end_of_algorithm()', 'transform')
    # Only a valid aggregate earns the period report. build_report refuses an
    # invalid one, and that refusal here would turn a Completed run_valid=false
    # run into a Runtime Error whose three statistics the result reader may not
    # open, losing the reason the run was invalid.
    end[0].body = ast.parse("""aggregate = self._arv2_driver.on_end_of_algorithm()
if aggregate['run_valid'] is True:
    report = build_report(self._arv2_driver._account_observations,
        evaluation_sessions=self._arv2_driver._evaluation_sessions,
        ar_percent=AR_PERCENT, source_profile_sha256=self._arv2_driver._profile['profile_sha256'],
        account_path_schema=ACCOUNT_PATH_SCHEMA, legacy_aggregate=aggregate)
    self.set_summary_statistic(STATISTIC_NAME, canonical_report_bytes(report).decode('ascii'))
""".replace('AR_PERCENT', str(percent))).body
    sources['main.py'] = ast.unparse(ast.fix_missing_locations(tree)) + '\n'
    buffers = tuple(sorted((name, raw.encode('ascii')) for name, raw in sources.items()))
    require(len(buffers) == 18 and all(0 < len(raw) <= 64000 for _, raw in buffers)
        and sum(len(raw) for _, raw in buffers) + base.MINIMUM_REVIEW_MARGIN_BYTES
            <= base.MAXIMUM_TOTAL_SOURCE_BYTES, 'bound')
    for name, raw in buffers: base._audit_source(name, raw)
    # The actual final flat closure is executed/audited for every arm.
    with relaxed._cloud_loader(sources) as (load, _):
        final = load(TILT[:-3]).require_tilt_profile()
        require(canonical(final) == canonical(profile), 'profile')
        load('legacy_six_october_reporting')
    return buffers, profile


def _geometry(axis):
    from datetime import date
    require(type(axis) is tuple and len(axis) == 3466 and tuple(sorted(set(axis))) == axis
        and sha(canonical(axis)) == '4ac84a2d01e18691a152812851857195ef56dac16b82ceb72bcf7dd068f86585', 'period')
    sessions = tuple(day for day in axis if '2021-01-04' <= day <= '2026-10-13')
    decisions, seen = [], set()
    for day in sessions:
        week = date.fromisoformat(day).isocalendar()[:2]
        if week not in seen: decisions.append(day); seen.add(week)
    require(len(sessions) == 1451 and len(decisions) == 302
        and sessions[0] == decisions[0] == '2021-01-04'
        and sessions[-1] == '2026-10-13' and decisions[-1] == '2026-10-12', 'period')
    return sessions, tuple(decisions)


def _bindings(bindings):
    require(type(bindings) is tuple and len(bindings) == 6151, 'bindings')
    digest = hashlib.sha256()
    for row in bindings:
        require(type(row) is dict, 'bindings')
        digest.update(canonical(row) + b'\n')
    require(digest.hexdigest() == '73ba4ac73c0485b2d274c31b5ec740a97a64de27a4f6dfbfb9cb63bc8e7cd15f', 'bindings')
    selected = [row for row in bindings if row.get('diagnostic_current_ticker') == 'QCOM']
    require(len(selected) == 1 and type(selected[0].get('security_id')) is str
        and sha(selected[0]['security_id'].encode('utf8')) == matched.QCOM_EXCLUSION_SECURITY_ID_SHA256, 'bindings')
    return selected[0]['security_id']


def prepare(october_package, *, axis, bindings, source_pairs, reporting_source, deadline):
    """Pure buffers under the caller's genuine-input/source normal-return guard."""
    budget(deadline)
    try: wrapped = october.require_october_order_input_package(october_package)
    except october.OctoberOrderInputPackageError: raise Refused('input') from None
    require(wrapped is october_package and wrapped.package.package_sha256 == OCTOBER_PACKAGE
        and wrapped.lineage_sha256 == OCTOBER_LINEAGE, 'input')
    sessions, decisions = _geometry(axis); qcom = _bindings(bindings)
    activation_object = wrapped.package.upload_objects[-1]
    activation = {name: getattr(activation_object, name) for name in ('object_store_key', 'content_sha256', 'byte_count')}
    require(activation == {'object_store_key': 'arv2/preliminary-rating/27645603c1a6e0fc9fa81655/transport-manifest.json',
        'content_sha256': '70f64450a44bedfa8ea371ac74a00e2134045fb79b433b93f0114be652bc6147', 'byte_count': 4631}, 'input')
    require(type(reporting_source) is bytes and reporting_source.isascii()
        and pin(reporting_source) == REPORTING_SOURCE_PIN, 'source_pin')
    historical = reconstruct_historical(source_pairs, qcom_security_id=qcom,
        manifest=HISTORICAL_MANIFEST, deadline=deadline)
    cells, public = [], []
    for percent, old_sources, old_profile in historical:
        budget(deadline)
        sources, profile = _extend_cell(percent, old_sources, old_profile,
            activation=activation, reporting_source=reporting_source)
        records = [{'project_path': name, **pin(raw)} for name, raw in sources]
        row = {'ar_percent': percent, 'candidate_id': f'R343-AR{percent:03d}',
            'profile_pin': pin(canonical(profile)), 'sources': records,
            'original_profile_sha256': old_profile['profile_sha256']}
        public.append(row)
        cells.append({**row, 'profile': profile,
            'source_pairs': [[name, raw.decode('ascii')] for name, raw in sources]})
    summary = {'schema': SCHEMA, 'research_epoch_id': EPOCH, 'cell_count': 7,
        'evaluation_start': sessions[0], 'evaluation_end': sessions[-1], 'evaluation_count': len(sessions),
        'decision_count': len(decisions), 'last_decision': decisions[-1],
        'package_sha256': OCTOBER_PACKAGE, 'lineage_sha256': OCTOBER_LINEAGE,
        'activation': activation, 'cells': public, **FALSE_FLAGS}
    validate_summary(summary)
    bundle = {'schema': SCHEMA + '-private', 'summary': summary, 'cells': cells, 'activation': activation}
    require(len(canonical(bundle)) <= 8*1024*1024, 'bound')
    validate_bundle(bundle)
    return {'summary': summary, 'bundle': bundle}


def validate_summary(value):
    keys = {'schema','research_epoch_id','cell_count','evaluation_start','evaluation_end','evaluation_count',
        'decision_count','last_decision','package_sha256','lineage_sha256','activation','cells',*FALSE_FLAGS}
    require(type(value) is dict and set(value) == keys and value['schema'] == SCHEMA
        and value['research_epoch_id'] == EPOCH and type(value['cell_count']) is int and value['cell_count'] == 7
        and value['evaluation_start'] == '2021-01-04' and value['evaluation_end'] == '2026-10-13'
        and type(value['evaluation_count']) is int and value['evaluation_count'] == 1451
        and type(value['decision_count']) is int and value['decision_count'] == 302
        and value['last_decision'] == '2026-10-12' and value['package_sha256'] == OCTOBER_PACKAGE
        and value['lineage_sha256'] == OCTOBER_LINEAGE and all(value[k] is False for k in FALSE_FLAGS), 'output')
    require(type(value['activation']) is dict and set(value['activation']) == {'object_store_key','content_sha256','byte_count'}
        and canonical(value['activation']) == canonical({'object_store_key': 'arv2/preliminary-rating/27645603c1a6e0fc9fa81655/transport-manifest.json',
        'content_sha256':'70f64450a44bedfa8ea371ac74a00e2134045fb79b433b93f0114be652bc6147','byte_count':4631}), 'output')
    require(type(value['cells']) is list and len(value['cells']) == 7, 'output')
    def valid_pin(row):
        return type(row) is dict and set(row) == {'byte_count','sha256'} and type(row['byte_count']) is int \
            and 0 < row['byte_count'] <= 2*1024*1024 and type(row['sha256']) is str \
            and len(row['sha256']) == 64 and all(c in '0123456789abcdef' for c in row['sha256'])
    expected_names = set(source_names()) | {'main.py','legacy_six_october_reporting.py'}
    for percent, row, old in zip(AR_PERCENTS, value['cells'], HISTORICAL_MANIFEST['candidates'], strict=True):
        require(type(row) is dict and set(row) == {'ar_percent','candidate_id','profile_pin','sources','original_profile_sha256'}
            and type(row['ar_percent']) is int and row['ar_percent'] == percent
            and row['candidate_id'] == f'R343-AR{percent:03d}'
            and row['original_profile_sha256'] == old['profile_sha256'] and valid_pin(row['profile_pin'])
            and type(row['sources']) is list and len(row['sources']) == 18, 'output')
        names = []
        for source in row['sources']:
            require(type(source) is dict and set(source) == {'project_path','byte_count','sha256'}
                and type(source['project_path']) is str and source['project_path'] in expected_names
                and valid_pin({k:source[k] for k in ('byte_count','sha256')}) and source['byte_count'] <= 64000, 'output')
            names.append(source['project_path'])
            if source['project_path'] == 'legacy_six_october_reporting.py':
                require({k:source[k] for k in ('byte_count','sha256')} == REPORTING_SOURCE_PIN, 'output')
        require(names == sorted(expected_names), 'output')
        require(sum(source['byte_count'] for source in row['sources']) + base.MINIMUM_REVIEW_MARGIN_BYTES
            <= base.MAXIMUM_TOTAL_SOURCE_BYTES, 'output')
    return value


def validate_bundle(value):
    require(type(value) is dict and set(value) == {'schema','summary','cells','activation'}
        and value['schema'] == SCHEMA + '-private', 'output')
    validate_summary(value['summary'])
    require(canonical(value['activation']) == canonical(value['summary']['activation'])
        and type(value['cells']) is list and len(value['cells']) == 7, 'output')
    for public, cell in zip(value['summary']['cells'], value['cells'], strict=True):
        require(type(cell) is dict and set(cell) == {*public,'profile','source_pairs'}
            and canonical({k:cell[k] for k in public}) == canonical(public)
            and type(cell['profile']) is dict and pin(canonical(cell['profile'])) == public['profile_pin']
            and cell['profile'].get('candidate_id') == public['candidate_id']
            and cell['profile'].get('research_epoch_id') == EPOCH
            and type(cell['source_pairs']) is list and len(cell['source_pairs']) == 18, 'output')
        for row, source in zip(public['sources'], cell['source_pairs'], strict=True):
            require(type(source) is list and len(source) == 2 and source[0] == row['project_path']
                and type(source[1]) is str and source[1].isascii()
                and pin(source[1].encode('ascii')) == {k:row[k] for k in ('byte_count','sha256')}, 'output')
    return value


def profile_record():
    return {'schema': SCHEMA, 'research_epoch_id': EPOCH, 'host_source_pins': dict(HOST_SOURCE_PINS),
        'historical_manifest_sha256': '3fde7673114794db256336c7c738c185859dd46e3d9af0765aa1cd7d008e5b86',
        'original_arms': list(AR_PERCENTS), 'source_files_per_cell': 18,
        'reporting_source_pin': dict(REPORTING_SOURCE_PIN),
        'historical_reconstruction': 'frozen_public_source_rewrites_exact_seven_committed_profile_and_file_manifests_no_old_package_or_operator',
        'input': 'genuine_october_sealed_wrapper_plus_exact_supplied_fullaxis_and_binding_stream',
        'economics': 'successful_QCOM_restored_six_10pct_3verified_1positive_next_open_MOO_RAW_strict_same_session_closing_minute_repair_only',
        'period': ['2021-01-04','2026-10-13'], 'decision_count':302,'evaluation_count':1451,
        'reporting': 'actual_same_job_NAV_and_returned_legacy_aggregate_after_unchanged_run_valid_gates',
        'invalid_run_reporting': 'run_valid_false_stays_Completed_with_its_three_legacy_statistics_and_no_period_report',
        'output': 'private_ASCII_source_buffers_and_profiles_no_source_input_payloads', **FALSE_FLAGS}
