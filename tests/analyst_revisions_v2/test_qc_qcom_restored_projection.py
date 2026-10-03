"""Focused inverse and order-source proofs for QCOM admission restoration."""

import ast
import dataclasses
from decimal import Decimal

import pytest

from research.analyst_revisions_v2_qc import accepted_risk_matched_historical_projection as original
from research.analyst_revisions_v2_qc import accepted_risk_six_universe_order_relaxed_qc_projection as relaxed
from research.analyst_revisions_v2_qc import six_universe_qcom_restored_projection as subject
from tests.analyst_revisions_v2.test_qc_matched_historical_projection import package
from tests.analyst_revisions_v2.test_qc_relaxed_selection_source import _rows, _snapshots


def _sources(projection):
    return {item.project_path: item.source_bytes.decode("ascii") for item in projection.source_files}


class _NormalizeGeneratedIdentities(ast.NodeTransformer):
    def __init__(self, baseline_profile_sha256):
        self.baseline_profile_sha256 = baseline_profile_sha256

    def visit_Constant(self, node):
        if type(node.value) is str and (node.value in self.baseline_profile_sha256
                or node.value.startswith("arv2-six-")
                or node.value.startswith("matched_historical_")
                or node.value.startswith("matched_qcom_excluded_")
                or node.value.startswith("cap90_matched_historical_")
                or node.value.startswith("cap90_matched_qcom_excluded_")):
            node.value = "<versioned identity>"
        return node

    def visit_ClassDef(self, node):
        node.name = node.name.replace("QcomExcluded", "")
        return self.generic_visit(node)


@pytest.mark.parametrize("source_id,arm,slippage", (
    ("R231", "ar_off", 0), ("R232", "ar_on100", 0),
    ("R233", "ar_off", 5), ("R234", "ar_on100", 5)))
def test_inverse_exactly_recovers_original_executable_ast_except_versioned_identifiers(
        package, source_id, arm, slippage):
    source, source_profile = original.build_qcom_exclusion_projection(package, arm, slippage)
    restored, restored_profile = original.build_matched_historical_projection(package, arm, slippage)
    assert source.projection_sha256 == subject.PREDECESSOR_SHA256[source_id]
    source_files, restored_files = _sources(source), _sources(restored)
    assert source_files.keys() == restored_files.keys()
    security_id = original._authenticated_qcom_security_id(package)
    baselines = {source_profile["matched_baseline_profile_sha256"],
                 restored_profile["matched_baseline_profile_sha256"]}
    for path in source_files:
        inverse = subject.strip_qcom_exclusion(path, source_files[path], security_id=security_id)
        expected = ast.parse(restored_files[path])
        assert ast.dump(_NormalizeGeneratedIdentities(baselines).visit(inverse),
                        include_attributes=False) == ast.dump(
            _NormalizeGeneratedIdentities(baselines).visit(expected), include_attributes=False), path


@pytest.mark.parametrize("source_id,new_id,expected_fraction", (
    ("R235", "R900", "0.80"), ("R236", "R901", "1.20"),
    ("R237", "R902", "2.00"), ("R238", "R903", "0.00"),
    ("R239", "R904", "0.80"), ("R240", "R905", "1.20"),
    ("R241", "R906", "2.00"), ("R242", "R907", "0.00"),
    ("R243", "R908", "0.80"), ("R244", "R909", "1.20"),
    ("R245", "R910", "2.00"), ("R246", "R911", "0.00")))
def test_each_rule_family_retain_economics_but_admits_qcom_source(
        package, source_id, new_id, expected_fraction):
    old, old_profile = subject._predecessor(package, source_id)
    new, profile = subject.build_qcom_admitted_projection(package, source_id, new_id)
    assert old.projection_sha256 == subject.PREDECESSOR_SHA256[source_id]
    assert new.projection_sha256 != old.projection_sha256
    assert len(new.source_files) == 17
    assert new.package_sha256 == old.package_sha256
    assert new.activation_manifest_sha256 == old.activation_manifest_sha256
    assert profile["maximum_stock_weight_change_fraction"] == expected_fraction
    for key in ("target_gross_exposure", "modeled_fee_bps_per_side", "slippage_bps",
                "admission_leverage", "comparison_arm", "coverage_policy_id"):
        if key in old_profile:
            assert profile[key] == old_profile[key]
    assert "stock_exclusion_policy_id" not in profile
    assert "excluded_logical_security_sha256" not in profile
    sources = _sources(new)
    assert not any("EXCLUDED_QCOM_SECURITY_ID" in body or "qcom_excluded" in body
                   or "qcom-excluded" in body for body in sources.values())
    with relaxed._cloud_loader(sources) as (load, _):
        gate = load(relaxed._GATE_PATH[:-3])
        runtime = load(relaxed._TILT_RUNTIME_PATH[:-3])
        assert not hasattr(gate, "EXCLUDED_QCOM_SECURITY_ID")
        assert runtime.require_tilt_profile() == profile


@pytest.fixture(scope="module")
def admitted_on100(package):
    return subject.build_qcom_admitted_projection(package, "R232", "R920")[0]


@pytest.mark.parametrize("universe", ("SPY", "QQQ", "SOXX", "XLV", "REMX", "XLE"))
def test_qcom_is_eligible_and_a_missing_fresh_reference_still_refuses(
        package, admitted_on100, universe):
    with relaxed._cloud_loader(_sources(admitted_on100)) as (load, _):
        gate = load(relaxed._GATE_PATH[:-3])
        qcom = original._authenticated_qcom_security_id(package)
        rows = list(_rows(gate, universe))
        rows[0] = dataclasses.replace(rows[0], security_id=qcom,
            security_name="QCOM", pit_market_cap=Decimal("1000000000000"),
            firm_specific_score=Decimal("1000000"))
        construction = gate.build_six_universe_construction(
            _snapshots(gate, {universe: tuple(rows)}), gate.TOP10_CAP90_EXPLORATORY_PROFILE)
        sleeve = next(item for item in construction.sleeves if item.universe_id == universe)
        assert sleeve.coverage.valid
        assert qcom in sleeve.matched_security_ids
        # The inverse removes only the QCOM-specific early refusal. The
        # exact-session RAW reference check remains in the order runtime.
        order_source = _sources(admitted_on100)[subject._ORDER]
        assert "six-universe RAW reference price census is incomplete" in order_source
        assert "not_exact_same_session_closing_minute" in order_source


def test_changed_exclusion_anchor_refuses_instead_of_permissive_restoration(package):
    old, _ = subject._predecessor(package, "R231")
    security_id = original._authenticated_qcom_security_id(package)
    gate = _sources(old)[subject._GATE]
    altered = gate.replace("row.security_id != EXCLUDED_QCOM_SECURITY_ID",
                           "row.security_id != 'SOME_OTHER_ID'", 1)
    with pytest.raises(subject.QcomRestoredProjectionError,
                       match="exclusion guard changed|stock eligibility anchor changed"):
        subject.strip_qcom_exclusion(subject._GATE, altered, security_id=security_id)


def test_wrong_security_identity_cannot_be_used_to_strip_a_matching_fake_constant(package):
    old, _ = subject._predecessor(package, "R231")
    gate = _sources(old)[subject._GATE]
    real_id = original._authenticated_qcom_security_id(package)
    forged = gate.replace(repr(real_id), repr("FAKE_SECURITY_ID"), 1)
    with pytest.raises(subject.QcomRestoredProjectionError, match="security identity changed"):
        subject.strip_qcom_exclusion(subject._GATE, forged, security_id="FAKE_SECURITY_ID")


@pytest.mark.parametrize("new_id", ("R225", "R247", "R231", "R246", "R0248", "R248 ", "r900", True))
def test_existing_or_malformed_candidate_identity_refuses_before_package_access(new_id):
    with pytest.raises(subject.QcomRestoredProjectionError, match="identities are invalid"):
        subject.build_qcom_admitted_projection(object(), "R235", new_id)
