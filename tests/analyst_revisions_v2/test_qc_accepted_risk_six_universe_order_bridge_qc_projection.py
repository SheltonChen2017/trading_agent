"""The A3 admission bridge is a distinct, role-bound QC source projection."""

import ast
import hashlib
from pathlib import Path

import pytest

from research.analyst_revisions_v2_qc import (
    accepted_risk_delta_order_package as delta,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_order_qc_projection as baseline_projector,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_order_qc_runtime as baseline_runtime,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_order_targets as targets,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_order_bridge_qc_projection as subject,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_order_bridge_qc_runtime as bridge_runtime,
)


PACKAGE_PATH = Path(
    "artifacts/analyst_revisions_v2/"
    "accepted_risk_delta_order_package_20260918_01/"
    "arv2-preliminary-qc-package-7803b84f0841f9685a4951de"
)
EXPECTED_BRIDGE_PROJECTION_SHA256S = {
    targets.ROLE_SIGNAL: (
        "f75725c37cb5e66f7db4070fcf89a05d5efe29cda60b6fc75086615d622cce0d"
    ),
    targets.ROLE_MATCHED: (
        "186cb2bb3dbd2a37358c9c0b2dbfa86e1e685203dba33795eb192f74faa9feeb"
    ),
    targets.ROLE_SIX_ETF_BASKET: (
        "980528e2ae982c7c8e19e07b856a15b7c386b338acf66336abe2766ff512de80"
    ),
}
EXPECTED_BRIDGE_PROJECTION_BYTES = {
    targets.ROLE_SIGNAL: 394268,
    targets.ROLE_MATCHED: 394269,
    targets.ROLE_SIX_ETF_BASKET: 394276,
}


@pytest.fixture(scope="module")
def package():
    if not PACKAGE_PATH.is_dir():
        pytest.skip("local ignored delta package is unavailable on this host")
    return delta.load_accepted_risk_delta_order_package(
        PACKAGE_PATH,
        expected_package_sha256=delta.EXPECTED_DELTA_PACKAGE_SHA256,
        expected_lineage_sha256=delta.EXPECTED_DELTA_LINEAGE_SHA256,
    )


@pytest.mark.parametrize("role", targets.ROLES)
def test_bridge_preserves_baseline_and_changes_only_entrypoint_plus_runtime(
    package, role,
):
    baseline = baseline_projector.build_accepted_risk_six_universe_order_qc_projection(
        package, role=role, variant=baseline_runtime.CAP90_VARIANT,
    )
    bridged = subject.build_accepted_risk_six_universe_order_bridge_qc_projection(
        package, role=role,
    )
    assert baseline.projection_sha256 == subject.PINNED_BASE_PROJECTION_SHA256S[role]
    assert baseline.profile_sha256 == subject.PINNED_BASE_PROFILE_SHA256S[role]
    assert bridged.projection_sha256 == EXPECTED_BRIDGE_PROJECTION_SHA256S[role]
    assert bridged.total_source_byte_count == EXPECTED_BRIDGE_PROJECTION_BYTES[role]
    assert bridged.projection_sha256 != baseline.projection_sha256
    assert bridged.profile_sha256 == subject.PINNED_BRIDGE_PROFILE_SHA256S[role]
    assert bridged.schema == subject.PROJECTION_SCHEMA
    assert bridged.variant == bridge_runtime.BRIDGE_VARIANT
    assert bridged.role == role
    assert bridged.package_sha256 == baseline.package_sha256
    assert bridged.activation_manifest_sha256 == baseline.activation_manifest_sha256
    assert bridged.backtest_only is True
    assert bridged.market_on_open_orders_only is True
    assert not any((
        bridged.live_orders, bridged.paper_orders, bridged.funded_orders,
        bridged.deployment, bridged.trading,
    ))
    assert len(bridged.source_files) == 14
    assert bridged.total_source_byte_count + baseline_projector.MINIMUM_REVIEW_MARGIN_BYTES <= (
        baseline_projector.MAXIMUM_TOTAL_SOURCE_BYTES
    )
    baseline_files = {item.project_path: item.source_bytes for item in baseline.source_files}
    bridge_files = {item.project_path: item.source_bytes for item in bridged.source_files}
    assert set(bridge_files) == set(baseline_files) | {subject.BRIDGE_RUNTIME_PATH}
    assert all(
        bridge_files[path] == content
        for path, content in baseline_files.items()
        if path != "main.py"
    )
    main = bridge_files["main.py"].decode("ascii")
    assert main.count("self.universe_settings.leverage = 2") == 1
    assert main.count("                leverage=2,\n") == 1
    assert "                leverage=1,\n" not in main
    assert "AcceptedRiskSixUniverseOrderBridgeQcDriver(" in main
    assert f"role={role!r}" in main
    assert f"variant={bridge_runtime.BRIDGE_VARIANT!r}" in main
    assert "market_on_open_order" not in main
    for item in bridged.source_files:
        text = item.source_bytes.decode("ascii")
        assert len(text) <= baseline_projector.MAXIMUM_QC_SOURCE_CHARACTERS
        assert not any(
            isinstance(node, ast.ImportFrom) and node.module == "__future__"
            for node in ast.walk(ast.parse(text))
        )
        compile("from AlgorithmImports import *\n" + text, item.project_path, "exec")


def test_bridge_fails_closed_on_baseline_profile_and_runtime_source_drift(
    package, monkeypatch,
):
    role = targets.ROLE_SIGNAL
    monkeypatch.setitem(subject.PINNED_BASE_PROJECTION_SHA256S, role, "0" * 64)
    with pytest.raises(subject.SixUniverseBridgeQcProjectionError, match="reviewed cap-90"):
        subject.build_accepted_risk_six_universe_order_bridge_qc_projection(
            package, role=role,
        )
    monkeypatch.undo()
    monkeypatch.setitem(subject.PINNED_BRIDGE_PROFILE_SHA256S, role, "0" * 64)
    with pytest.raises(subject.SixUniverseBridgeQcProjectionError, match="bridge role profile"):
        subject.build_accepted_risk_six_universe_order_bridge_qc_projection(
            package, role=role,
        )
    monkeypatch.undo()
    monkeypatch.setattr(subject, "PINNED_BRIDGE_RUNTIME_SHA256", "0" * 64)
    with pytest.raises(subject.SixUniverseBridgeQcProjectionError, match="runtime changed"):
        subject.build_accepted_risk_six_universe_order_bridge_qc_projection(
            package, role=role,
        )


def test_bridge_rejects_new_capability_and_oversized_runtime(package, monkeypatch):
    path = Path(subject.__file__).resolve().parent / subject.BRIDGE_RUNTIME_PATH
    original = path.read_bytes()
    hostile = original + b"\nimport requests\n"
    monkeypatch.setattr(
        subject, "PINNED_BRIDGE_RUNTIME_SHA256", hashlib.sha256(hostile).hexdigest(),
    )
    monkeypatch.setattr(subject, "_read_exact_bridge_runtime", lambda: hostile)
    with pytest.raises(subject.SixUniverseBridgeQcProjectionError, match="forbidden capability"):
        subject.build_accepted_risk_six_universe_order_bridge_qc_projection(
            package, role=targets.ROLE_SIGNAL,
        )

    sized = original + b"\n#" + b"x" * (
        baseline_projector.MAXIMUM_QC_SOURCE_CHARACTERS - len(original)
    )
    assert len(sized) > baseline_projector.MAXIMUM_QC_SOURCE_CHARACTERS
    assert len(sized) < baseline_projector.MAXIMUM_SOURCE_FILE_BYTES
    monkeypatch.setattr(
        subject, "PINNED_BRIDGE_RUNTIME_SHA256", hashlib.sha256(sized).hexdigest(),
    )
    monkeypatch.setattr(subject, "_read_exact_bridge_runtime", lambda: sized)
    with pytest.raises(subject.SixUniverseBridgeQcProjectionError, match="per-file bound"):
        subject.build_accepted_risk_six_universe_order_bridge_qc_projection(
            package, role=targets.ROLE_SIGNAL,
        )
