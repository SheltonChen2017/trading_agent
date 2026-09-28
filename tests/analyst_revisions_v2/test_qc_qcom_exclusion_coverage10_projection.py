"""Offline proofs for the separately versioned QCOM-excluded 10% floors."""

import ast
import dataclasses
from decimal import Decimal
import hashlib

import pytest

from research.analyst_revisions_v2_qc import accepted_risk_matched_historical_projection as prior
from research.analyst_revisions_v2_qc import accepted_risk_six_universe_order_relaxed_qc_projection as relaxed
from research.analyst_revisions_v2_qc import six_universe_qcom_exclusion_coverage10_projection as subject
from tests.analyst_revisions_v2.test_qc_matched_historical_projection import package
from tests.analyst_revisions_v2.test_qc_relaxed_selection_source import _rows, _snapshots


_NEW_PROJECTIONS = {
    "ar_off": "26e4680967e6f4a6bc66b0fe7c3e4198cdab1db2f1a7357878f01952560fd654",
    "ar_on80": "b3037679192d13cd931f22dd27ff7443ea328d17a7bed5d294bed3754f97dc9d",
    "ar_on120": "bf62a1fcf62bee8d63a739d88220a8d8764a30b889baaa1bca0ef025a7264f4f",
    "ar_on200": "ddaf84b437d347f43f789377b9629f90120d8418edfed3e7c596cfecf7e33f18",
}
_NEW_PROFILES = {
    "ar_off": "347b5fc991e49873af17242d02e3f10c3ad96305b9ad19dab0665b9a13bd145d",
    "ar_on80": "ba0992f1b35b184b9ba87b49f5f2cb0622e8aaf03bab81b9ba11ac58fb9690af",
    "ar_on120": "118e83a0aa53a792e169aea2dad7af007f56dbefa496ff9e6f150e510c68b0bf",
    "ar_on200": "af27b27e22f565a1ded18ad55b0e29705f87b803753a4fb3d9dc1433281689c7",
}


def _sources(value):
    return {item.project_path: item.source_bytes.decode("ascii") for item in value.source_files}


@pytest.fixture(scope="module")
def family(package):
    predecessors = {
        "ar_off": prior.build_qcom_exclusion_projection(package, "ar_off", 0),
        **{f"ar_on{percent}": prior.build_qcom_exclusion_tilt_projection(package, percent, 0)
           for percent in (80, 120, 200)},
    }
    successors = {arm: subject.build_qcom_exclusion_coverage10_projection(package, arm)
                  for arm in subject.ARMS}
    return predecessors, successors


@pytest.mark.parametrize("arm", (None, True, 0, "ar_on100", "ar_on80_s5", "ar_off_s5"))
def test_invalid_arm_refuses_before_package_access(arm):
    with pytest.raises(subject.QcomCoverage10ProjectionError, match="coverage10 arm"):
        subject.build_qcom_exclusion_coverage10_projection(object(), arm)


def test_old_25_percent_sources_remain_exact_and_new_four_arm_lineage_is_distinct(family):
    predecessors, successors = family
    assert subject.COVERAGE_POLICY == tuple(
        (name, "0.10", "0.10", "0.10", 5) for name in (
            "SPY", "QQQ", "SOXX", "XLV", "REMX", "XLE"))
    assert len(set(_NEW_PROJECTIONS.values())) == len(set(_NEW_PROFILES.values())) == 4
    for arm, ((old, old_profile), (new, profile)) in (
            (arm, (predecessors[arm], successors[arm])) for arm in subject.ARMS):
        assert old.projection_sha256 == subject.PREDECESSOR_PROJECTION_SHA256[arm]
        assert new.projection_sha256 == _NEW_PROJECTIONS[arm]
        assert new.profile_sha256 == profile["profile_sha256"] == _NEW_PROFILES[arm]
        assert new.schema == f"arv2-six-matched-qcom-excluded-coverage10-{arm}-projection-v1"
        assert new.role == profile["role"] == f"matched_qcom_excluded_coverage10_{arm}_s0"
        assert new.variant == f"coverage10_matched_qcom_excluded_{arm}_s0_v1"
        assert new.profile_id == profile["profile_id"] == (
            f"arv2-six-matched-qcom-excluded-coverage10-{arm}-s0-profile-v1")
        assert profile["schema"] == f"arv2-six-matched-qcom-excluded-coverage10-{arm}-profile-v1"
        assert profile["coverage_policy_id"] == subject.COVERAGE_POLICY_ID
        assert profile["comparison_arm"] == arm
        assert profile["matched_baseline_profile_sha256"] != old_profile[
            "matched_baseline_profile_sha256"]
        assert (new.package_sha256, new.activation_manifest_sha256) == (
            old.package_sha256, old.activation_manifest_sha256)
        for key, expected in (("target_gross_exposure", "0.98"),
                              ("modeled_fee_bps_per_side", "10"), ("slippage_bps", "0"),
                              ("admission_leverage", "2"),
                              ("stock_exclusion_policy_id", prior.QCOM_EXCLUSION_POLICY_ID),
                              ("excluded_logical_security_sha256",
                               prior.QCOM_EXCLUSION_SECURITY_ID_SHA256),
                              ("maximum_stock_weight_change_fraction",
                               "0.00" if arm == "ar_off" else
                               f"{int(arm[5:]) // 100}.{int(arm[5:]) % 100:02d}")):
            assert profile[key] == old_profile[key] == expected
        previous = _sources(old)
        sources = _sources(new)
        assert len(sources) == len(previous) == 17
        assert {path for path in sources if sources[path] != previous[path]} == (
            set(subject._SCHEMA_ASSIGNMENTS) | {"main.py"})
        assert new.total_source_byte_count + subject._base.MINIMUM_REVIEW_MARGIN_BYTES <= (
            subject._base.MAXIMUM_TOTAL_SOURCE_BYTES)
        assert all(item.byte_count == len(item.source_bytes)
                   and item.content_sha256 == hashlib.sha256(item.source_bytes).hexdigest()
                   and item.byte_count <= subject._base.MAXIMUM_QC_SOURCE_CHARACTERS
                   for item in new.source_files)
        with relaxed._cloud_loader(sources) as (load, _):
            gate = load(relaxed._GATE_PATH[:-3])
            runtime = load(relaxed._TILT_RUNTIME_PATH[:-3])
            assert gate.RELAXED_COVERAGE_POLICY == subject.COVERAGE_POLICY
            assert gate.TOP10_CAP90_EXPLORATORY_PROFILE.to_record()[
                "coverage_policy_id"] == subject.COVERAGE_POLICY_ID
            assert runtime.require_tilt_profile() == profile
            assert runtime.TILT_META_SCHEMA == (
                f"arv2-six-matched-qcom-excluded-coverage10-{arm}-meta-v1")
            assert runtime.TILT_SUMMARY_SCHEMA == (
                f"arv2-six-matched-qcom-excluded-coverage10-{arm}-summary-v1")
            assert load("accepted_risk_six_universe_order_qc_runtime").META_SCHEMA == (
                runtime.TILT_META_SCHEMA)
        tilt_runtime = ast.parse(sources[relaxed._TILT_RUNTIME_PATH])
        aggregate = next(node for node in ast.walk(tilt_runtime)
                         if isinstance(node, ast.FunctionDef) and node.name == "_aggregate")
        disclosures = [node.args[0] for node in ast.walk(aggregate)
                       if isinstance(node, ast.Call)
                       and ast.unparse(node.func) == "aggregate.update"
                       and len(node.args) == 1 and isinstance(node.args[0], ast.Dict)]
        assert len(disclosures) == 1
        assert [key.value for key in disclosures[0].keys].count("coverage_policy_id") == 1
        assert ast.literal_eval(disclosures[0].values[
            [key.value for key in disclosures[0].keys].index("coverage_policy_id")]) == (
            subject.COVERAGE_POLICY_ID)


@pytest.mark.parametrize("arm", subject.ARMS)
@pytest.mark.parametrize("universe", subject._selection.ALL25_UNIVERSES)
def test_all_six_sleeves_admit_12_percent_verified_coverage_but_not_25_percent(
        family, package, arm, universe):
    predecessors, successors = family
    old, _ = predecessors[arm]
    new, _ = successors[arm]
    qcom_id = prior._authenticated_qcom_security_id(package)
    for projection, expected_valid in ((old, False), (new, True)):
        with relaxed._cloud_loader(_sources(projection)) as (load, _):
            gate = load(relaxed._GATE_PATH[:-3])
            rows = list(_rows(gate, universe, count=50, positives=12,
                              weight="0.02", known=6))
            rows[0] = dataclasses.replace(rows[0], security_id=qcom_id,
                                          security_name="QCOM")
            snapshot = _snapshots(gate, {universe: tuple(rows)})
            construction = gate.build_six_universe_construction(
                snapshot, gate.TOP10_CAP90_EXPLORATORY_PROFILE)
            sleeve = next(item for item in construction.sleeves
                          if item.universe_id == universe)
            assert sleeve.coverage.mapping_ratio == Decimal("0.12")
            assert sleeve.coverage.cap_weight_coverage_ratio == Decimal("0.12")
            assert sleeve.coverage.valid is expected_valid
            if expected_valid:
                assert sleeve.coverage.member_count == 50
                assert sleeve.coverage.mapped_member_count == 6
                assert qcom_id not in sleeve.matched_security_ids
                assert len(sleeve.matched_security_ids) == 5
                assert sum((weight for _, weight in sleeve.matched_stock_weights), Decimal(0)) <= (
                    sleeve.budget * Decimal("0.12"))
                assert sleeve.matched_etf_fallback_weight > 0
            else:
                assert not sleeve.matched_security_ids
                assert sleeve.matched_etf_fallback_weight == sleeve.budget


def test_10_percent_total_floor_and_five_verified_names_remain_distinct(family):
    _predecessors, successors = family
    projection, _ = successors["ar_off"]
    with relaxed._cloud_loader(_sources(projection)) as (load, _):
        gate = load(relaxed._GATE_PATH[:-3])
        universe = "XLE"
        cases = (
            (50, "0.02", 5, True, ()),
            (20, "0.005", 20, True, ()),
            (20, "0.00495", 20, False, ("TOTAL_REPORTED_WEIGHT_OUT_OF_RANGE",)),
            (20, "0.05", 4, False, ("KNOWN_MARKET_CAP_NAME_COUNT_BELOW_MINIMUM",)),
            (100, "0.01", 9, False, ("SID_NAME_MAPPING_BELOW_MINIMUM",
                                            "MARKET_CAP_WEIGHT_COVERAGE_BELOW_MINIMUM")),
        )
        for count, weight, known, valid, reasons in cases:
            rows = _rows(gate, universe, count=count, positives=12,
                         weight=weight, known=known)
            construction = gate.build_six_universe_construction(
                _snapshots(gate, {universe: rows}), gate.TOP10_CAP90_EXPLORATORY_PROFILE)
            sleeve = next(item for item in construction.sleeves if item.universe_id == universe)
            assert sleeve.coverage.valid is valid
            assert sleeve.coverage.refusal_reasons == reasons


def test_changed_predecessor_policy_or_role_refuses_exact_render_anchor(family):
    predecessors, _successors = family
    predecessor, profile = predecessors["ar_off"]
    gate_source = _sources(predecessor)[relaxed._GATE_PATH]
    mutation = gate_source.replace("'0.25'", "'0.24'", 1)
    with pytest.raises(subject.QcomCoverage10ProjectionError, match="predecessor policy"):
        subject._render_source(relaxed._GATE_PATH, mutation, predecessor, profile, "ar_off")
    main_source = _sources(predecessor)["main.py"]
    class_name = "ARV2MatchedHistoricalArOffS0QcomExcludedAlgorithm"
    assert sum(isinstance(node, ast.ClassDef) and node.name == class_name
               for node in ast.parse(main_source).body) == 1
    with pytest.raises(subject.QcomCoverage10ProjectionError, match="identity anchor"):
        subject._render_source("main.py", main_source.replace(class_name, "OtherAlgorithm"),
                               predecessor, profile, "ar_off")
