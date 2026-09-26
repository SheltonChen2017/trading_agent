"""Two complementary in-memory mutations; no QC or outcome authority."""

import ast
import dataclasses

import pytest

from research.analyst_revisions_v2_qc import accepted_risk_six_universe_order_relaxed_qc_projection as sut
from tests.analyst_revisions_v2 import test_qc_recent_coverage_projection as inputs
from tests.analyst_revisions_v2 import test_qc_relaxed_selection_source as fixtures

prior_package = inputs.prior_package
actual_package = inputs.actual_package


@pytest.fixture(scope="module")
def off(prior_package, actual_package):
    return sut.build_full_ar_ablation_projection(prior_package, actual_package, False)


def sources(projection):
    return {item.project_path: item.source_bytes.decode("ascii") for item in projection.source_files}


def restore_function(module, source, name):
    node = next(node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef)
                and node.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), "in-memory-mutant.py", "exec"), module.__dict__)


def test_off_does_not_visit_transfer_code_and_restoring_zero_tilt_traversal_is_detected(off, monkeypatch):
    with sut._cloud_loader(sources(off[0])) as (load, _):
        tilt = load("accepted_risk_six_universe_order_tilt_targets")
        gate = tilt._gate
        snapshots = fixtures._snapshots(gate)  # Distinct finite nonzero scores.
        construction = gate.build_six_universe_construction(snapshots, gate.TOP10_CAP90_EXPLORATORY_PROFILE)
        def forbidden(*args, **kwargs):
            raise AssertionError("economic AR-off traversed transfer sizing")
        monkeypatch.setattr(tilt, "_transfer_capacity", forbidden)
        assert tilt.tilt_matched_weights(construction, snapshots) == construction.matched_weights
        assert tilt.MAXIMUM_STOCK_WEIGHT_CHANGE_FRACTION == 0
        # Restore only the original function; the zero fraction remains. Mere
        # zero-tilt weighting still traverses score ranking/capacity and is red.
        restore_function(tilt, (fixtures.ROOT / "accepted_risk_six_universe_order_tilt_targets.py").read_text(),
                         "tilt_matched_weights")
        with pytest.raises(AssertionError, match="transfer sizing"):
            tilt.tilt_matched_weights(construction, snapshots)


def test_restoring_ar_entry_is_detected_without_an_earlier_lineage_refusal(off):
    with sut._cloud_loader(sources(off[0])) as (load, _):
        gate = load("accepted_risk_six_universe_gate")
        snapshots = fixtures._snapshots(gate, {name: tuple(dataclasses.replace(row, firm_specific_score=None)
            for row in fixtures._rows(gate, name)) for name in gate.UNIVERSE_IDS})
        expected = gate.build_six_universe_construction(snapshots, gate.TOP10_CAP90_EXPLORATORY_PROFILE)
        assert all(len(sleeve.matched_security_ids) == 10 for sleeve in expected.sleeves)
        restore_function(gate, (fixtures.ROOT / "accepted_risk_six_universe_gate.py").read_text(), "_selected_ids")
        mutant = gate.build_six_universe_construction(snapshots, gate.TOP10_CAP90_EXPLORATORY_PROFILE)
        assert all(not sleeve.matched_security_ids for sleeve in mutant.sleeves if sleeve.universe_id != "XLE")
