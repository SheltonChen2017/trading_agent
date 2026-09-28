"""One QCOM-excluded historical AR-entry arm with no weight transfer.

The R232 source supplies the identical score-dependent admission and
cap-ranked stock count. Only the transfer fraction and this arm's immutable
identity change; the previously launched source and manifest stay frozen.
"""

import dataclasses
import hashlib
import json

from . import accepted_risk_matched_historical_projection as prior
from . import accepted_risk_six_universe_order_qc_projection as base
from . import accepted_risk_six_universe_order_relaxed_qc_projection as relaxed


class QcomEntryOnlyProjectionError(ValueError):
    """The R232 predecessor or the zero-transfer source differs."""


PREDECESSOR_PROJECTION_SHA256 = "87c3ecd2a36522f101086afeaf0bf19758757267f59035db2fb169e23bd3e803"
PREDECESSOR_BASELINE_PROFILE_SHA256 = "f03e7f0f9669e3d5168511a9c05cf5e0b9c2c88801fc87433d990537c333615d"
ECONOMIC_USAGE = "entry_and_count_no_weight_transfer"


def build_qcom_entry_only_projection(package):
    """Project a distinct 2021--2025 physical-order diagnostic, not R232 A2."""
    predecessor, old_profile = prior.build_qcom_exclusion_projection(package, "ar_on100", 0)
    if (predecessor.projection_sha256 != PREDECESSOR_PROJECTION_SHA256
            or old_profile["matched_baseline_profile_sha256"]
                != PREDECESSOR_BASELINE_PROFILE_SHA256):
        raise QcomEntryOnlyProjectionError("R232 exact predecessor changed")
    sources = {}
    for item in predecessor.source_files:
        path = item.project_path
        source = prior._render_qcom_exclusion_tilt(path, item.source_bytes.decode("ascii"), 0)
        if path == relaxed._TILT_RUNTIME_PATH:
            if source.count('entry_count_and_weight') != 2:
                raise QcomEntryOnlyProjectionError("AR economic-use disclosure anchor changed")
            source = source.replace('entry_count_and_weight', ECONOMIC_USAGE)
        sources[path] = source
    changed = {path for path, text in sources.items()
               if text.encode("ascii") != next(item.source_bytes for item in predecessor.source_files
                                               if item.project_path == path)}
    if changed != {relaxed._TILT_TARGET_PATH, relaxed._TILT_RUNTIME_PATH, "main.py"}:
        raise QcomEntryOnlyProjectionError("AR-entry-only source topology changed")
    with relaxed._cloud_loader(sources) as (load, _):
        runtime = load(relaxed._TILT_RUNTIME_PATH[:-3])
        tilt = load(relaxed._TILT_TARGET_PATH[:-3])
        gate = load(relaxed._GATE_PATH[:-3])
        profile = runtime.require_tilt_profile()
        runtime.expected_tilt_custom_statistic_names()
        if (profile.get("role") != "matched_qcom_excluded_ar_on0_s0"
                or profile.get("comparison_arm") != "ar_on0"
                or profile.get("analyst_revision_economic_usage") != ECONOMIC_USAGE
                or profile.get("maximum_stock_weight_change_fraction") != "0.00"
                or profile.get("matched_baseline_profile_sha256")
                    != PREDECESSOR_BASELINE_PROFILE_SHA256
                or profile.get("modeled_fee_bps_per_side") != "10"
                or profile.get("slippage_bps") != "0"
                or profile.get("admission_leverage") != "2"
                or profile.get("target_gross_exposure") != "0.98"
                or profile.get("stock_exclusion_policy_id") != prior.QCOM_EXCLUSION_POLICY_ID
                or profile.get("excluded_logical_security_sha256")
                    != prior.QCOM_EXCLUSION_SECURITY_ID_SHA256
                or str(tilt.MAXIMUM_STOCK_WEIGHT_CHANGE_FRACTION) != "0.00"
                or gate.MINIMUM_POSITIVE_SCORE_COUNT != 5
                or runtime.TILT_META_SCHEMA != "arv2-six-matched-qcom-excluded-tilt0-meta-v1"
                or runtime.TILT_SUMMARY_SCHEMA != "arv2-six-matched-qcom-excluded-tilt0-summary-v1"
                or load("accepted_risk_six_universe_order_qc_runtime").META_SCHEMA
                    != prior.QCOM_EXCLUSION_META_SCHEMA):
            raise QcomEntryOnlyProjectionError("AR-entry-only role, gate, economics or transport changed")
    files = tuple(sorted((base._source_file(path, source.encode("ascii"))
                          for path, source in sources.items()), key=lambda item: item.project_path))
    total = sum(item.byte_count for item in files)
    if (len(files) != 17 or len({item.project_path for item in files}) != 17
            or any(item.byte_count > base.MAXIMUM_QC_SOURCE_CHARACTERS for item in files)
            or total + base.MINIMUM_REVIEW_MARGIN_BYTES > base.MAXIMUM_TOTAL_SOURCE_BYTES):
        raise QcomEntryOnlyProjectionError("AR-entry-only QC source budget changed")
    for item in files:
        base._audit_source(item.project_path, item.source_bytes)
    value = dataclasses.replace(predecessor,
        schema="arv2-six-matched-qcom-excluded-entry-only-projection-v1",
        role=profile["role"], variant="cap90_matched_qcom_excluded_ar_on0_s0_v1",
        profile_id=profile["profile_id"], profile_sha256=profile["profile_sha256"],
        source_files=files, total_source_byte_count=total)
    semantic = {key: item for key, item in value.to_record().items()
                if key not in ("projection_id", "projection_sha256")}
    digest = hashlib.sha256(base._canonical(semantic)).hexdigest()
    return dataclasses.replace(value, projection_sha256=digest,
        projection_id="arv2-six-matched-qcom-excluded-entry-only-projection-" + digest[:24]), json.loads(
            base._canonical(profile))
