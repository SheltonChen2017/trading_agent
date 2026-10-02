"""The v4 tilt cloud source is a distinct, closed projection of R182."""

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
    accepted_risk_six_universe_order_bridge_qc_projection as bridge_projector,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_order_bridge_qc_runtime as bridge_runtime,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_order_tilt_qc_projection as subject,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_order_tilt_qc_runtime as tilt_runtime,
)


PACKAGE_PATH = Path(
    "artifacts/analyst_revisions_v2/"
    "accepted_risk_delta_order_package_20260918_01/"
    "arv2-preliminary-qc-package-7803b84f0841f9685a4951de"
)


@pytest.fixture(scope="module")
def package():
    if not PACKAGE_PATH.is_dir():
        pytest.skip("local ignored delta package is unavailable on this host")
    return delta.load_accepted_risk_delta_order_package(
        PACKAGE_PATH,
        expected_package_sha256=delta.EXPECTED_DELTA_PACKAGE_SHA256,
        expected_lineage_sha256=delta.EXPECTED_DELTA_LINEAGE_SHA256,
    )


def test_tilt_is_distinct_and_preserves_exact_r181_r182_bridge_source(package):
    old_signal = baseline_projector.build_accepted_risk_six_universe_order_qc_projection(
        package, role="signal", variant=baseline_runtime.CAP90_VARIANT,
    )
    old_matched = bridge_projector.build_accepted_risk_six_universe_order_bridge_qc_projection(
        package, role="matched",
    )
    value = subject.build_accepted_risk_six_universe_order_tilt_qc_projection(
        package
    )
    assert old_signal.projection_sha256 == (
        "b68661ec2f90f98eb47e09242b8b9d4cd8ed21101667f355afba0a4a48461c29"
    )
    assert old_matched.projection_sha256 == subject.PINNED_BASE_MATCHED_PROJECTION_SHA256
    assert old_matched.variant == bridge_runtime.BRIDGE_VARIANT
    assert value.schema == subject.PROJECTION_SCHEMA
    assert value.projection_sha256 == (
        "8fdb1e051c1e9620c1a126dd9d2bd09c1eb298d9dd8ae1d4e7d07ada61af9afc"
    )
    assert value.projection_sha256 not in (
        old_signal.projection_sha256, old_matched.projection_sha256,
    )
    assert value.role == "matched_revision_tilt"
    assert value.variant == tilt_runtime.TILT_VARIANT
    assert value.profile_sha256 == subject.PINNED_TILT_PROFILE_SHA256
    assert value.to_record()["variant"] == tilt_runtime.TILT_VARIANT
    assert value.package_sha256 == old_matched.package_sha256
    assert value.activation_manifest_sha256 == old_matched.activation_manifest_sha256
    assert len(value.source_files) == 16
    assert value.total_source_byte_count == 422728

    old_files = {
        item.project_path: item.source_bytes for item in old_matched.source_files
        if item.project_path != "main.py"
    }
    new_files = {
        item.project_path: item.source_bytes for item in value.source_files
    }
    assert all(new_files[path] == content for path, content in old_files.items())
    assert set(new_files) == set(old_files) | {
        "main.py",
        "accepted_risk_six_universe_order_tilt_targets.py",
        "accepted_risk_six_universe_order_tilt_qc_runtime.py",
    }
    main = new_files["main.py"].decode("ascii")
    assert "class ARV2SixUniverseOrderTiltAlgorithm(QCAlgorithm):" in main
    assert "AcceptedRiskSixUniverseOrderTiltQcDriver(" in main
    assert "role='matched_revision_tilt'" in main
    assert f"variant={tilt_runtime.TILT_VARIANT!r}" in main
    assert "self.universe_settings.leverage = 2" in main
    assert "                leverage=2,\n" in main
    assert "                leverage=1,\n" not in main
    assert "accepted_risk_six_universe_order_bridge_qc_runtime.py" in new_files
    assert "BridgeQcDriver" in new_files["accepted_risk_six_universe_order_bridge_qc_runtime.py"].decode("ascii")
    assert "set_start_date(2020, 11, 1)" in main
    assert "set_end_date(2025, 12, 31)" in main
    assert "market_on_open_order" not in main


def test_every_tilt_bridge_file_is_prelude_safe_and_within_qc_bound(package):
    value = subject.build_accepted_risk_six_universe_order_tilt_qc_projection(
        package
    )
    assert value.total_source_byte_count + baseline_projector.MINIMUM_REVIEW_MARGIN_BYTES <= (
        baseline_projector.MAXIMUM_TOTAL_SOURCE_BYTES
    )
    for item in value.source_files:
        text = item.source_bytes.decode("ascii")
        assert len(text) <= baseline_projector.MAXIMUM_QC_SOURCE_CHARACTERS
        assert not any(
            isinstance(node, ast.ImportFrom) and node.module == "__future__"
            for node in ast.walk(ast.parse(text))
        )
        compile("from AlgorithmImports import *\n" + text, item.project_path, "exec")


def test_tilt_refuses_baseline_profile_and_tilt_source_drift(
    package, monkeypatch,
):
    monkeypatch.setattr(
        subject, "PINNED_BASE_MATCHED_PROJECTION_SHA256", "0" * 64,
    )
    with pytest.raises(subject.SixUniverseTiltQcProjectionError, match="R182 bridge matched"):
        subject.build_accepted_risk_six_universe_order_tilt_qc_projection(package)
    monkeypatch.undo()

    monkeypatch.setattr(subject, "PINNED_TILT_PROFILE_SHA256", "0" * 64)
    with pytest.raises(subject.SixUniverseTiltQcProjectionError, match="bridge revision tilt profile"):
        subject.build_accepted_risk_six_universe_order_tilt_qc_projection(package)
    monkeypatch.undo()

    path = "accepted_risk_six_universe_order_tilt_targets.py"
    monkeypatch.setitem(subject._TILT_SOURCE_SHA256S, path, "0" * 64)
    with pytest.raises(subject.SixUniverseTiltQcProjectionError, match="source bytes changed"):
        subject.build_accepted_risk_six_universe_order_tilt_qc_projection(package)


def test_tilt_refuses_added_io_capability_and_oversized_non_runtime_file(
    package, monkeypatch,
):
    path = "accepted_risk_six_universe_order_tilt_targets.py"
    original = (Path(subject.__file__).resolve().parent / path).read_bytes()
    hostile = original + b"\nimport requests\n"
    monkeypatch.setitem(
        subject._TILT_SOURCE_SHA256S, path, hashlib.sha256(hostile).hexdigest()
    )
    monkeypatch.setattr(subject, "_read_exact_tilt_source", lambda _path: hostile)
    with pytest.raises(subject.SixUniverseTiltQcProjectionError, match="forbidden capability"):
        subject.build_accepted_risk_six_universe_order_tilt_qc_projection(package)

    sized = original + b"\n#" + b"x" * (
        baseline_projector.MAXIMUM_QC_SOURCE_CHARACTERS - len(original)
    )
    assert len(sized) > baseline_projector.MAXIMUM_QC_SOURCE_CHARACTERS
    assert len(sized) < baseline_projector.MAXIMUM_SOURCE_FILE_BYTES
    monkeypatch.setitem(
        subject._TILT_SOURCE_SHA256S, path, hashlib.sha256(sized).hexdigest()
    )
    monkeypatch.setattr(subject, "_read_exact_tilt_source", lambda _path: sized)
    with pytest.raises(subject.SixUniverseTiltQcProjectionError, match="per-file bound"):
        subject.build_accepted_risk_six_universe_order_tilt_qc_projection(package)
