"""Offline arithmetic and frozen-source checks for three prospective AR-on arms."""

from decimal import Decimal, ROUND_DOWN, localcontext
import hashlib

import pytest

from research.analyst_revisions_v2_qc import accepted_risk_matched_historical_projection as subject
from tests.analyst_revisions_v2.test_qc_matched_historical_projection import package
from tests.analyst_revisions_v2.test_qc_relaxed_selection_source import _snapshots


_OLD_PROJECTIONS = {
    ("ar_off", 0): "0c6a4c5a7cd3bffacb9d4148b5167fe0d1b38b8617b3c01fd974f2639a76704b",
    ("ar_on100", 0): "87c3ecd2a36522f101086afeaf0bf19758757267f59035db2fb169e23bd3e803",
    ("ar_off", 5): "f1a6fb92823dea0c15a70ebef9b5dddebdfb9f5ba58be3e617815659832b02e5",
    ("ar_on100", 5): "6637b2fa86e25135446d90af59af44ced2f9cde03d0f4dfa1d2c185d6aade1f9",
}
_NEW_PROJECTIONS = {
    80: "06842824c2fee60f447c4e920ee23634917958f94fa2332a9f21ea24eeed0aa1",
    120: "cc18bcdda7dc17750c186a403c8ec74568c4a7f71c528bdd4b714c00ef63c17b",
    200: "44b7e0dfcd31ecb1698e0b46196ebe4de80ca036d9273516b05f35dd65241f25",
}
_NEW_PROFILES = {
    80: "7db16708228b5864b17d5d7aa2c132478085bc56b6a711a1cf3b50f90a52c7b9",
    120: "578404e182995779dff97fda0f9030879f4702cbfba141024feb521217ba9805",
    200: "a22141b0022f5032911d19dc3a837eac291c632263cc013e2a4843afd84cb22d",
}
_CHANGED_FILES = {
    "accepted_risk_six_universe_order_tilt_targets.py",
    "accepted_risk_six_universe_order_tilt_qc_runtime.py",
    "main.py",
}


def _sources(projection):
    return {item.project_path: item.source_bytes.decode("ascii") for item in projection.source_files}


@pytest.fixture(scope="module")
def family(package):
    old = {(arm, slip): subject.build_qcom_exclusion_projection(package, arm, slip)
           for arm, slip in _OLD_PROJECTIONS}
    new = {percent: subject.build_qcom_exclusion_tilt_projection(package, percent)
           for percent in _NEW_PROJECTIONS}
    return old, new


@pytest.mark.parametrize("percent,slippage", ((True, 0), (100, 0), (0, 0),
    (140, 0), (80.0, 0), (80, True), (80, 5), (80, -1)))
def test_invalid_tilt_or_slippage_refuses_before_input_access(percent, slippage):
    with pytest.raises(subject.MatchedHistoricalProjectionError):
        subject.build_qcom_exclusion_tilt_projection(object(), percent, slippage)


def test_old_projections_remain_exact_and_new_sources_have_separate_identities(family):
    old, new = family
    for key, expected in _OLD_PROJECTIONS.items():
        assert old[key][0].projection_sha256 == expected
    predecessor, baseline_profile = old["ar_on100", 0]
    predecessor_sources = _sources(predecessor)
    assert baseline_profile["matched_baseline_profile_sha256"] == (
        "f03e7f0f9669e3d5168511a9c05cf5e0b9c2c88801fc87433d990537c333615d")
    for percent, (projection, profile) in new.items():
        arm = f"ar_on{percent}"
        fraction = f"{percent // 100}.{percent % 100:02d}"
        sources = _sources(projection)
        assert projection.projection_sha256 == _NEW_PROJECTIONS[percent]
        assert profile["profile_sha256"] == projection.profile_sha256 == _NEW_PROFILES[percent]
        assert projection.schema == f"arv2-six-matched-qcom-excluded-tilt{percent}-projection-v1"
        assert projection.role == profile["role"] == f"matched_qcom_excluded_{arm}_s0"
        assert projection.variant == f"cap90_matched_qcom_excluded_{arm}_s0_v1"
        assert projection.profile_id == profile["profile_id"] == (
            f"arv2-six-matched-qcom-excluded-{arm}-s0-profile-v1")
        assert profile["schema"] == f"arv2-six-matched-qcom-excluded-tilt{percent}-profile-v1"
        assert profile["comparison_arm"] == arm
        assert profile["maximum_stock_weight_change_fraction"] == fraction
        assert profile["matched_baseline_profile_sha256"] == baseline_profile[
            "matched_baseline_profile_sha256"]
        for key in ("package_sha256", "activation_manifest_sha256"):
            assert getattr(projection, key) == getattr(predecessor, key)
        for key, expected in (("target_gross_exposure", "0.98"),
                              ("modeled_fee_bps_per_side", "10"), ("slippage_bps", "0"),
                              ("admission_leverage", "2")):
            assert profile[key] == expected
        assert profile["stock_exclusion_policy_id"] == subject.QCOM_EXCLUSION_POLICY_ID
        assert profile["excluded_logical_security_sha256"] == subject.QCOM_EXCLUSION_SECURITY_ID_SHA256
        assert set(sources) == set(predecessor_sources) and len(sources) == 17
        assert {path for path in sources if sources[path] != predecessor_sources[path]} == _CHANGED_FILES
        assert projection.total_source_byte_count + subject._base.MINIMUM_REVIEW_MARGIN_BYTES <= (
            subject._base.MAXIMUM_TOTAL_SOURCE_BYTES)
        assert all(item.byte_count <= subject._base.MAXIMUM_QC_SOURCE_CHARACTERS
                   and item.byte_count == len(item.source_bytes)
                   and item.content_sha256 == hashlib.sha256(item.source_bytes).hexdigest()
                   for item in projection.source_files)
        with subject._relaxed._cloud_loader(sources) as (load, _):
            runtime = load(subject._relaxed._TILT_RUNTIME_PATH[:-3])
            assert runtime.require_tilt_profile() == profile
            assert runtime.TILT_META_SCHEMA == f"arv2-six-matched-qcom-excluded-tilt{percent}-meta-v1"
            assert runtime.TILT_SUMMARY_SCHEMA == f"arv2-six-matched-qcom-excluded-tilt{percent}-summary-v1"


def test_transfer_is_percent_of_own_post_cap_weight_and_guards_stay_active(family):
    _old, new = family
    top_weights = []
    for percent, (projection, _profile) in new.items():
        with subject._relaxed._cloud_loader(_sources(projection)) as (load, _):
            tilt = load("accepted_risk_six_universe_order_tilt_targets")
            gate = tilt._gate
            snapshots = _snapshots(gate)
            construction = gate.build_six_universe_construction(
                snapshots, gate.TOP10_CAP90_EXPLORATORY_PROFILE)
            baseline = {item.security_id: item.weight for item in construction.matched_weights
                        if item.asset_kind == "stock"}
            tilted = tilt.tilt_matched_weights(construction, snapshots)
            actual = {item.security_id: item.weight for item in tilted if item.asset_kind == "stock"}
            top = "sid-XLE-00"
            with localcontext() as context:
                context.prec = 96
                expected_transfer = (baseline[top] * Decimal(percent) / 100).quantize(
                    Decimal("1e-30"), rounding=ROUND_DOWN)
                assert actual[top] - baseline[top] == expected_transfer
                assert sum((item.weight for item in tilted), Decimal(0)) == Decimal("0.98")
                assert sum((item.weight for item in tilted if item.asset_kind == "etf"), Decimal(0)) == (
                    sum((item.weight for item in construction.matched_weights
                         if item.asset_kind == "etf"), Decimal(0)))
            assert all(Decimal(0) < weight <= gate.DIRECT_STOCK_WEIGHT_CAP
                       for weight in actual.values())
            assert tilt.MAXIMUM_STOCK_WEIGHT_CHANGE_FRACTION == Decimal(percent) / 100
            top_weights.append(actual[top])
    assert top_weights == sorted(top_weights) and len(set(top_weights)) == 3


def test_exact_source_anchor_change_refuses():
    path = subject._relaxed._TILT_TARGET_PATH
    with pytest.raises(subject.MatchedHistoricalProjectionError, match="exact source anchor"):
        subject._render_qcom_exclusion_tilt(path, "TILT_ROLE = 'changed'\n", 80)
