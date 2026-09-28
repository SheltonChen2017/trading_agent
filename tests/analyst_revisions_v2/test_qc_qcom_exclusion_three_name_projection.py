"""Focused behavioral proofs for the new three-name QCOM-excluded closure."""

import ast
import dataclasses
from decimal import Decimal
import hashlib

import pytest

from research.analyst_revisions_v2_qc import accepted_risk_six_universe_order_relaxed_qc_projection as relaxed
from research.analyst_revisions_v2_qc import six_universe_qcom_exclusion_coverage10_projection as prior
from research.analyst_revisions_v2_qc import six_universe_qcom_exclusion_three_name_projection as subject
from tests.analyst_revisions_v2.test_qc_matched_historical_projection import package
from tests.analyst_revisions_v2.test_qc_relaxed_selection_source import _rows, _snapshots


_PROJECTION_SHA256 = {
    "ar_off": "829c370e58ebd1d398cc62a0acd5aca29885487f0353a5ff0ab7157afeb58ced",
    "ar_on80": "ca4546db5e649d55da0fa266a8876760d487e7984559fc512d9c64bb0e42277d",
    "ar_on120": "f72bc3f00065d259af10480ce7c2a99f55826da8ab419b50aab6529c7194b10c",
    "ar_on200": "954aeea6c375659d7dfd6d8357cde1a70623287f4cdc7581f4e3a4070a650e35",
}
_PROFILE_SHA256 = {
    "ar_off": "df467b66aea1852f0863e5a8a30a5aac48e4d42eb6f693315805fa90a20cc88f",
    "ar_on80": "d658ca16667a09aa11b3e631a5bebc618b1b6dc6cec93ea9286471a8bfec7d18",
    "ar_on120": "d068b0d9795f0b636ba8c90a6cfbdcd657a6839b8830fbb3c83a80bd5eba3ea7",
    "ar_on200": "17674a77ce2fc2efd0bb7206abc0f85f05f4b9527b324466f4e03e1f686c33f0",
}


def _sources(value):
    return {item.project_path: item.source_bytes.decode("ascii") for item in value.source_files}


@pytest.fixture(scope="module")
def family(package):
    old = {arm: prior.build_qcom_exclusion_coverage10_projection(package, arm)
           for arm in subject.ARMS}
    new = {arm: subject.build_qcom_exclusion_three_name_projection(package, arm)
           for arm in subject.ARMS}
    return old, new


@pytest.mark.parametrize("arm", (None, True, 0, "ar_on100", "ar_on80_s5", "ar_off_s5"))
def test_invalid_arm_refuses_before_package_access(arm):
    with pytest.raises(subject.QcomThreeNameProjectionError, match="three-name arm"):
        subject.build_qcom_exclusion_three_name_projection(object(), arm)


def test_frozen_10_percent_predecessors_remain_exact_and_new_identity_is_distinct(family):
    old, new = family
    assert subject.COVERAGE_POLICY == tuple(
        (name, "0.10", "0.10", "0.10", 3) for name in (
            "SPY", "QQQ", "SOXX", "XLV", "REMX", "XLE"))
    assert len(set(_PROJECTION_SHA256.values())) == len(set(_PROFILE_SHA256.values())) == 4
    for arm in subject.ARMS:
        predecessor, old_profile = old[arm]
        successor, profile = new[arm]
        assert predecessor.projection_sha256 == subject.PREDECESSOR_PROJECTION_SHA256[arm]
        assert successor.projection_sha256 == _PROJECTION_SHA256[arm]
        assert successor.profile_sha256 == profile["profile_sha256"] == _PROFILE_SHA256[arm]
        assert successor.schema == f"arv2-six-matched-qcom-excluded-three-name-{arm}-projection-v1"
        assert successor.role == profile["role"] == f"matched_qcom_excluded_three_name_{arm}_s0"
        assert successor.variant == f"three_name_matched_qcom_excluded_{arm}_s0_v1"
        assert successor.profile_id == profile["profile_id"] == (
            f"arv2-six-matched-qcom-excluded-three-name-{arm}-s0-profile-v1")
        assert profile["schema"] == f"arv2-six-matched-qcom-excluded-three-name-{arm}-profile-v1"
        assert profile["coverage_policy_id"] == subject.COVERAGE_POLICY_ID
        assert profile["comparison_arm"] == arm
        assert profile["matched_baseline_profile_sha256"] != old_profile[
            "matched_baseline_profile_sha256"]
        assert (successor.package_sha256, successor.activation_manifest_sha256) == (
            predecessor.package_sha256, predecessor.activation_manifest_sha256)
        for key in ("target_gross_exposure", "modeled_fee_bps_per_side", "slippage_bps",
                    "admission_leverage", "stock_exclusion_policy_id",
                    "excluded_logical_security_sha256",
                    "maximum_stock_weight_change_fraction"):
            assert profile[key] == old_profile[key]
        assert profile["target_gross_exposure"] == "0.98"
        assert profile["modeled_fee_bps_per_side"] == "10"
        assert profile["slippage_bps"] == "0"
        assert profile["admission_leverage"] == "2"
        before, after = _sources(predecessor), _sources(successor)
        assert len(before) == len(after) == 17
        assert {path for path in after if after[path] != before[path]} == (
            set(prior._SCHEMA_ASSIGNMENTS) | {"main.py"})
        assert successor.total_source_byte_count + subject._base.MINIMUM_REVIEW_MARGIN_BYTES <= (
            subject._base.MAXIMUM_TOTAL_SOURCE_BYTES)
        assert all(item.byte_count == len(item.source_bytes)
                   and item.content_sha256 == hashlib.sha256(item.source_bytes).hexdigest()
                   and item.byte_count <= subject._base.MAXIMUM_QC_SOURCE_CHARACTERS
                   for item in successor.source_files)
        with relaxed._cloud_loader(after) as (load, _):
            gate = load(relaxed._GATE_PATH[:-3])
            runtime = load(relaxed._TILT_RUNTIME_PATH[:-3])
            assert gate.RELAXED_COVERAGE_POLICY == subject.COVERAGE_POLICY
            assert gate.MINIMUM_POSITIVE_SCORE_COUNT == 3
            assert gate.TOP10_CAP90_EXPLORATORY_PROFILE.to_record()[
                "minimum_positive_score_count"] == (0 if arm == "ar_off" else 3)
            assert gate.TOP10_CAP90_EXPLORATORY_PROFILE.to_record()[
                "coverage_policy_id"] == subject.COVERAGE_POLICY_ID
            assert runtime.require_tilt_profile() == profile
            assert runtime.TILT_META_SCHEMA == (
                f"arv2-six-matched-qcom-excluded-three-name-{arm}-meta-v1")
            assert runtime.TILT_SUMMARY_SCHEMA == (
                f"arv2-six-matched-qcom-excluded-three-name-{arm}-summary-v1")
            assert load("accepted_risk_six_universe_order_qc_runtime").META_SCHEMA == (
                runtime.TILT_META_SCHEMA)


@pytest.mark.parametrize("arm", subject.ARMS)
@pytest.mark.parametrize("universe", subject._prior._selection.ALL25_UNIVERSES)
def test_three_known_names_admit_stock_but_two_refuse_with_own_etf_fallback(family, arm, universe):
    old, new = family
    for projection, known, valid in ((old[arm][0], 3, False),
                                     (new[arm][0], 2, False),
                                     (new[arm][0], 3, True)):
        with relaxed._cloud_loader(_sources(projection)) as (load, _):
            gate = load(relaxed._GATE_PATH[:-3])
            rows = _rows(gate, universe, count=20, positives=3 if arm != "ar_off" else 0,
                         weight="0.05", known=known)
            construction = gate.build_six_universe_construction(
                _snapshots(gate, {universe: rows}), gate.TOP10_CAP90_EXPLORATORY_PROFILE)
            sleeve = next(item for item in construction.sleeves if item.universe_id == universe)
            assert sleeve.coverage.mapping_ratio == Decimal(known) / 20
            assert sleeve.coverage.cap_weight_coverage_ratio == Decimal(known) / 20
            assert sleeve.coverage.valid is valid
            if valid:
                assert len(sleeve.matched_security_ids) == 3
                assert sleeve.matched_etf_fallback_weight > 0
            else:
                assert not sleeve.matched_security_ids
                assert sleeve.matched_etf_fallback_weight == sleeve.budget
                assert "KNOWN_MARKET_CAP_NAME_COUNT_BELOW_MINIMUM" in sleeve.coverage.refusal_reasons


@pytest.mark.parametrize("arm", ("ar_on80", "ar_on120", "ar_on200"))
def test_active_non_xle_positive_score_floor_is_three_not_two_or_five(family, arm):
    old, new = family
    for projection, count, stock in ((old[arm][0], 3, False),
                                     (new[arm][0], 2, False),
                                     (new[arm][0], 3, True)):
        with relaxed._cloud_loader(_sources(projection)) as (load, _):
            gate = load(relaxed._GATE_PATH[:-3])
            rows = _rows(gate, "QQQ", count=20, positives=count,
                         weight="0.05", known=6)
            result = gate.build_six_universe_construction(
                _snapshots(gate, {"QQQ": rows}), gate.TOP10_CAP90_EXPLORATORY_PROFILE)
            sleeve = next(item for item in result.sleeves if item.universe_id == "QQQ")
            assert sleeve.coverage.valid and sleeve.positive_score_count == count
            assert bool(sleeve.matched_security_ids) is stock
            assert sleeve.matched_etf_fallback_weight > 0


def test_unknown_and_qcom_ids_remain_outside_stock_selection(family, package):
    _old, new = family
    projection, _profile = new["ar_on80"]
    qcom_id = prior._matched._authenticated_qcom_security_id(package)
    with relaxed._cloud_loader(_sources(projection)) as (load, _):
        gate = load(relaxed._GATE_PATH[:-3])
        rows = list(_rows(gate, "XLE", count=20, positives=0, weight="0.05", known=5))
        rows[0] = dataclasses.replace(rows[0], security_id=qcom_id, security_name="QCOM")
        result = gate.build_six_universe_construction(
            _snapshots(gate, {"XLE": tuple(rows)}), gate.TOP10_CAP90_EXPLORATORY_PROFILE)
        sleeve = next(item for item in result.sleeves if item.universe_id == "XLE")
        assert sleeve.coverage.valid
        assert qcom_id not in sleeve.matched_security_ids
        assert len(sleeve.matched_security_ids) >= 3
        assert all(item is not None for item in sleeve.matched_security_ids)
        assert sleeve.matched_etf_fallback_weight > 0


@pytest.mark.parametrize("arm", ("ar_off", "ar_on80"))
def test_exact_three_verified_names_including_qcom_keep_coverage_but_exclude_stock(
        family, package, arm):
    _old, new = family
    projection, _profile = new[arm]
    qcom_id = prior._matched._authenticated_qcom_security_id(package)
    with relaxed._cloud_loader(_sources(projection)) as (load, _):
        gate = load(relaxed._GATE_PATH[:-3])
        rows = list(_rows(gate, "SOXX", count=20, positives=3, weight="0.05", known=3))
        rows[0] = dataclasses.replace(rows[0], security_id=qcom_id, security_name="QCOM")
        construction = gate.build_six_universe_construction(
            _snapshots(gate, {"SOXX": tuple(rows)}), gate.TOP10_CAP90_EXPLORATORY_PROFILE)
        sleeve = next(item for item in construction.sleeves if item.universe_id == "SOXX")
        assert sleeve.coverage.valid
        assert sleeve.coverage.mapped_member_count == 3
        assert qcom_id not in sleeve.matched_security_ids
        if arm == "ar_off":
            assert sleeve.matched_security_ids == tuple(row.security_id for row in rows[1:3])
            assert sleeve.matched_etf_fallback_weight < sleeve.budget
        else:
            assert sleeve.positive_score_count == 2
            assert sleeve.signal_security_ids == sleeve.matched_security_ids == ()
            assert sleeve.matched_etf_fallback_weight == sleeve.budget


def test_mutated_policy_score_or_main_identity_refuses_exact_render_anchor(family):
    old, _new = family
    predecessor, _profile = old["ar_on80"]
    sources = _sources(predecessor)
    gate_source = sources[relaxed._GATE_PATH]
    assert gate_source.count("MINIMUM_POSITIVE_SCORE_COUNT = 5") == 1
    with pytest.raises(subject.QcomThreeNameProjectionError, match="positive-score"):
        subject._render_source(relaxed._GATE_PATH,
            gate_source.replace("MINIMUM_POSITIVE_SCORE_COUNT = 5",
                                "MINIMUM_POSITIVE_SCORE_COUNT = 4"), predecessor, "ar_on80")
    tree = ast.parse(gate_source)
    assignment = subject._assignment(tree, "RELAXED_COVERAGE_POLICY")
    assert ast.literal_eval(assignment.value) == prior.COVERAGE_POLICY
    with pytest.raises(subject.QcomThreeNameProjectionError, match="predecessor coverage policy"):
        subject._render_source(relaxed._GATE_PATH,
            gate_source.replace("('SPY', '0.10', '0.10', '0.10', 5)",
                                "('SPY', '0.10', '0.10', '0.10', 4)"), predecessor, "ar_on80")
    main_source = sources["main.py"]
    expected_class = "ARV2MatchedHistoricalArOn80S0QcomExcludedCoverage10Algorithm"
    assert expected_class in main_source
    with pytest.raises(subject.QcomThreeNameProjectionError, match="anchor"):
        subject._render_source("main.py", main_source.replace(expected_class, "OtherAlgorithm"),
                               predecessor, "ar_on80")
