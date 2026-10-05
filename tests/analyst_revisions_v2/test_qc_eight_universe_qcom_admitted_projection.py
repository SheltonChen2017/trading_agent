"""Offline source-closure proofs for the prospective eight-universe order family.

These are source-only candidates.  No XLI/XLF callback, outcome, or QC access
is implied by successful local projection.
"""

import ast
from decimal import Decimal

import pytest

from research.analyst_revisions_v2_qc import accepted_risk_six_universe_order_relaxed_qc_projection as relaxed
from research.analyst_revisions_v2_qc import eight_universe_qcom_admitted_projection as subject
from research.analyst_revisions_v2_qc import six_universe_qcom_restored_projection as restored
from tests.analyst_revisions_v2.test_qc_matched_historical_projection import package
from tests.analyst_revisions_v2.test_qc_relaxed_selection_source import _rows, _snapshots


def _sources(projection):
    return {item.project_path: item.source_bytes.decode("ascii")
            for item in projection.source_files}


@pytest.fixture(scope="module")
def family(package):
    return {arm: subject.build_eight_universe_projection(
        package, arm, subject.CANDIDATE_BY_ARM[arm]) for arm in subject.ARMS}


def test_every_arm_has_a_distinct_exact_17_file_order_closure(family):
    assert tuple(subject.CANDIDATE_BY_ARM) == subject.ARMS
    assert len({projection.projection_sha256 for projection, _ in family.values()}) == 9
    for arm, (projection, profile) in family.items():
        candidate = subject.CANDIDATE_BY_ARM[arm]
        assert projection.schema == f"arv2-eight-qcom-admitted-{candidate.lower()}-projection-v1"
        assert projection.role == profile["role"]
        assert projection.profile_id == profile["profile_id"]
        assert len(projection.source_files) == 17
        assert len({item.project_path for item in projection.source_files}) == 17
        assert projection.total_source_byte_count == sum(
            item.byte_count for item in projection.source_files)
        assert projection.total_source_byte_count + 32_768 <= 448 * 1024
        assert max(item.byte_count for item in projection.source_files) <= 64 * 1024
        assert profile["comparison_arm"] == arm
        assert profile["target_gross_exposure"] == "0.98"
        assert profile["modeled_fee_bps_per_side"] == "10"
        assert profile["slippage_bps"] == "0"
        assert profile["admission_leverage"] == "2"
        assert profile["maximum_stock_weight_change_fraction"] == (
            f"{int(arm[5:]) // 100}.{int(arm[5:]) % 100:02d}"
            if arm.startswith("ar_on") else "0.00")
        assert "qcom_excluded" not in "".join(_sources(projection).values())
        with relaxed._cloud_loader(_sources(projection)) as (load, _):
            gate = load(subject._GATE[:-3])
            order = load(subject._RUNTIME[:-3])
            tilt = load(subject._TILT_RUNTIME[:-3])
            assert gate.UNIVERSE_IDS == subject.UNIVERSES
            assert gate.RELAXED_COVERAGE_POLICY == subject.NEW_POLICY
            assert gate.SLEEVE_BUDGETS == (Decimal("0.1225"),) * 8
            assert sum(gate.SLEEVE_BUDGETS) == Decimal("0.98")
            assert gate.DIRECT_STOCK_WEIGHT_CAP == Decimal("0.098")
            assert gate.MINIMUM_POSITIVE_SCORE_COUNT == (
                3 if arm in ("ar_off", "eight_etf_basket") else 1)
            assert order.MAXIMUM_STATISTIC_BYTES == 16_384
            assert order.META_STATISTIC_NAME == subject.STATISTIC_NAMES[0]
            assert order.AGGREGATES_STATISTIC_NAME == subject.STATISTIC_NAMES[1]
            assert set(tilt.expected_tilt_custom_statistic_names()) == set(subject.STATISTIC_NAMES)
            assert tilt.require_tilt_profile() == profile


def test_two_qc_subscription_and_constituent_callback_loops_are_eight(family):
    for projection, _ in family.values():
        main = ast.parse(_sources(projection)["main.py"])
        loops = [node for node in ast.walk(main) if isinstance(node, ast.For)
                 and isinstance(node.iter, ast.Tuple)
                 and tuple(item.value for item in node.iter.elts
                           if isinstance(item, ast.Constant)) == subject.UNIVERSES]
        assert len(loops) == 2
        assert not any("EXCLUDED_QCOM_SECURITY_ID" in item.source_bytes.decode("ascii")
                       for item in projection.source_files)


def test_eight_panel_and_sleeve_geometry_are_explicitly_versioned(family):
    projection, _ = family["ar_on100"]
    sources = _sources(projection)
    diagnostics = sources[subject._DIAGNOSTICS]
    assert diagnostics.count("'eight_etf_panel_row_count'") >= 3
    assert "'six_etf_panel_row_count'" not in diagnostics
    assert "10040" in diagnostics and "7530" not in diagnostics
    assert "len(rows) != 40" in diagnostics and "len(rows) != 30" not in diagnostics
    with relaxed._cloud_loader(sources) as (load, _):
        diag = load(subject._DIAGNOSTICS[:-3])
        order = load(subject._RUNTIME[:-3])
        assert diag.SCHEMA == "arv2-eight-matched-historical-diagnostics-v1"
        assert diag.REFERENCE_REPAIR_SCHEMA == (
            "arv2-eight-matched-historical-diagnostics-v2-closing-minute")
        assert diag.MAXIMUM_STATISTIC_BYTES == 8192
        assert order._gate.UNIVERSE_IDS == subject.UNIVERSES
        assert "arv2-eight-universe-order-sleeve-summary-table-v1" in sources[subject._RUNTIME]


def test_basket_is_eight_actual_etfs_but_preserves_existing_status_inventory(family):
    projection, profile = family["eight_etf_basket"]
    sources = _sources(projection)
    assert profile["comparison_arm"] == "eight_etf_basket"
    assert profile["analyst_revision_economic_usage"] == "none_authenticated_score_clock_only"
    assert "status = 'SIX_ETF_BASKET'" in sources[subject._TARGETS]
    assert "EIGHT_ETF_BASKET" not in sources[subject._TARGETS]
    assert "'eight_etf_basket'" in sources[subject._TARGETS]
    assert "'six_etf_basket'" not in sources[subject._TARGETS]
    assert "six_frozen_sleeve_budgets_in_actual_etfs" not in sources[subject._GATE]
    assert "eight_frozen_sleeve_budgets_in_actual_etfs" in sources[subject._GATE]


def test_new_sleeves_use_the_same_one_score_gate_and_eight_etf_budget(family):
    projection, _ = family["ar_on100"]
    with relaxed._cloud_loader(_sources(projection)) as (load, _):
        gate = load(subject._GATE[:-3])
        overrides = {ticker: _rows(gate, ticker, positives=1)
                     for ticker in ("XLI", "XLF")}
        construction = gate.build_six_universe_construction(
            _snapshots(gate, overrides), gate.TOP10_CAP90_EXPLORATORY_PROFILE)
        assert tuple(item.universe_id for item in construction.sleeves) == subject.UNIVERSES
        for sleeve in construction.sleeves[-2:]:
            assert sleeve.coverage.valid
            assert len(sleeve.signal_security_ids) == 1
            assert len(sleeve.matched_security_ids) == 1
            assert sleeve.signal_etf_fallback_weight > 0
        assert [(item.security_id, item.weight) for item in
                construction.etf_basket_weights] == [
            (f"etf-{ticker}", Decimal("0.1225")) for ticker in subject.UNIVERSES]


def test_ar_off_really_selects_cap_ranked_stocks_when_all_scores_are_zero(package):
    projection, profile = subject.build_eight_universe_projection(package, "ar_off", "R268")
    assert profile["analyst_revision_economic_usage"] == "none_authenticated_score_clock_only"
    with relaxed._cloud_loader(_sources(projection)) as (load, _):
        gate = load(subject._GATE[:-3])
        targets = load(subject._TARGETS[:-3])
        snapshots = _snapshots(gate, {ticker: _rows(gate, ticker, positives=0)
                                      for ticker in subject.UNIVERSES})
        construction = gate.build_six_universe_construction(
            snapshots, gate.TOP10_CAP90_EXPLORATORY_PROFILE)
        assert tuple(item.universe_id for item in construction.sleeves) == subject.UNIVERSES
        for sleeve in construction.sleeves:
            assert sleeve.coverage.valid
            assert sleeve.positive_score_count == 0
            assert sleeve.matched_security_ids == tuple(
                f"sid-{sleeve.universe_id}-{index:02d}" for index in range(10))
            assert sleeve.signal_security_ids == sleeve.matched_security_ids
        assert len(construction.matched_weights) == 80
        assert all(not item.security_id.startswith("etf-")
                   for item in construction.matched_weights)
        assert sum(item.weight for item in construction.matched_weights) == Decimal("0.98")
        assert all(targets._sleeve_diagnostic(sleeve, targets.ROLE_MATCHED,
                   gate.TOP10_CAP90_EXPLORATORY_PROFILE).selection_status
                   == "FULL_STOCK_SLOTS" for sleeve in construction.sleeves)


@pytest.mark.parametrize("arm,candidate", (
    ("ar_off", "R269"), ("ar_on100", "R261"), ("ar_on60", "R280"),
    ("eight_etf_basket", "R275"), ("ar_off", True)))
def test_wrong_arm_or_candidate_refuses_before_package_access(arm, candidate):
    with pytest.raises(subject.EightUniverseProjectionError, match="arm or new candidate"):
        subject.build_eight_universe_projection(object(), arm, candidate)


def test_changed_six_parent_census_refuses_instead_of_silently_extending(package):
    predecessor, _ = restored.build_qcom_admitted_projection(package, "R242", "R255")
    sources = _sources(predecessor)
    source = sources[subject._GATE]
    altered = source.replace("UniverseSpec('SPY', 'SPY')",
                             "UniverseSpec('SPY', 'QQQ')", 1)
    assert altered != source
    with pytest.raises(subject.EightUniverseProjectionError,
                       match="parent six-member census changed"):
        subject._render(subject._GATE, altered, parent_id="R255",
                        new_id="R268", basket=False)
    diagnostic = sources[subject._DIAGNOSTICS]
    assert "7530" in diagnostic
    with pytest.raises(subject.EightUniverseProjectionError,
                       match="diagnostic geometry ancestor changed"):
        subject._render(subject._DIAGNOSTICS,
                        diagnostic.replace("7530", "7531", 1),
                        parent_id="R255", new_id="R268", basket=False)
    runtime = sources[subject._RUNTIME]
    assert "MAXIMUM_STATISTIC_BYTES = 8192" in runtime
    with pytest.raises(subject.EightUniverseProjectionError,
                       match="statistic bound ancestor changed"):
        subject._render(subject._RUNTIME, runtime.replace(
            "MAXIMUM_STATISTIC_BYTES = 8192",
            "MAXIMUM_STATISTIC_BYTES = 4096", 1),
            parent_id="R255", new_id="R268", basket=False)
