"""Dangerous-direction tests for the first SEP-3 extraction dry run."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.validate_sep3_extraction import (
    DEFAULT_MANIFEST,
    ExtractionValidationError,
    _git,
    _imported_modules,
    validate,
)


def _manifest() -> dict:
    return json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))


def _write_manifest(tmp_path: Path, manifest: dict) -> Path:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return path


def test_reviewed_extraction_dry_run_is_exact_and_not_authorized():
    result = validate()
    assert result["status"] == "valid-dry-run-not-ready-for-physical-extraction"
    assert result["source_commit"] == "e642469df7030deb1a36171f43a85e68e1fd82d1"
    assert result["inventory"] == {
        "tracked_paths": 734,
        "sha256": "853a139ca133103f838b66ec5c143566daae951bd2fea1a1f13576718ab72dcb",
        "assigned_exactly_once": True,
        "destination_counts": {
            "shared_contracts": 3,
            "strategy_research": 241,
            "trading_assistant": 490,
        },
    }
    assert result["physical_extraction_authorized"] is False
    assert result["surfaces"]["script_ownership_counts"] == {
        "trading_assistant": 8,
        "strategy_research": 56,
        "cross_product_composition": 11,
    }
    assert result["surfaces"]["launch_counts"] == {
        "trading_assistant": 7,
        "strategy_research": 54,
        "cross_product_composition": 10,
    }
    assert result["blockers"] == {
        "composition_files": 11,
        "python_crossing_roots": 6,
        "operator_database_importers": 4,
        "support_surface_partition": (
            "product-pure-tests-pinned-integration-explicit"
        ),
        "integration_test_files": 54,
        "shared_contract_test_files": 0,
        "shared_contract_test_surface": "pending",
        "governance_support_partition": "pending",
    }


def test_unclassified_retained_path_is_refused(tmp_path: Path):
    manifest = _manifest()
    manifest["data_destination"]["trading_assistant"].remove(
        "data/event_data.py"
    )
    with pytest.raises(ExtractionValidationError, match="exactly one destination"):
        validate(_write_manifest(tmp_path, manifest))


def test_authority_root_cannot_move_to_research(tmp_path: Path):
    manifest = _manifest()
    manifest["product_roots"]["trading_assistant"].remove("execution")
    manifest["product_roots"]["strategy_research"].append("execution")
    with pytest.raises(ExtractionValidationError, match="authority root escaped"):
        validate(_write_manifest(tmp_path, manifest))


def test_licensed_surface_cannot_move_to_assistant(tmp_path: Path):
    manifest = _manifest()
    manifest["product_roots"]["strategy_research"].remove("ml")
    manifest["product_roots"]["trading_assistant"].append("ml")
    with pytest.raises(ExtractionValidationError, match="licensed surface escaped"):
        validate(_write_manifest(tmp_path, manifest))


def test_vendor_client_cannot_enter_tiny_shared_package(tmp_path: Path):
    manifest = _manifest()
    source = manifest["source"]["reviewed_commit"]
    path = "data/market_data.py"
    manifest["data_destination"]["strategy_research"].remove(path)
    manifest["shared_contracts"]["source_to_package"][path] = (
        "agent_contracts/market_data.py"
    )
    manifest["shared_contracts"]["source_blob_ids"][path] = _git(
        "rev-parse", f"{source}:{path}"
    ).strip()
    with pytest.raises(ExtractionValidationError, match="shared contract import leakage"):
        validate(_write_manifest(tmp_path, manifest))


def test_shared_target_path_collision_is_refused(tmp_path: Path):
    manifest = copy.deepcopy(_manifest())
    manifest["shared_contracts"]["source_to_package"][
        "data/financial_primitives.py"
    ] = "agent_contracts/evidence_status.py"
    with pytest.raises(ExtractionValidationError, match="target collision"):
        validate(_write_manifest(tmp_path, manifest))


def test_test_partition_count_drift_is_refused(tmp_path: Path):
    manifest = _manifest()
    manifest["support_partition"]["test_counts"]["integration"] -= 1
    with pytest.raises(ExtractionValidationError, match="test support partition drifted"):
        validate(_write_manifest(tmp_path, manifest))


def test_test_partition_hash_drift_is_refused(tmp_path: Path):
    manifest = _manifest()
    manifest["support_partition"]["test_inventory_sha256"]["strategy_research"] = (
        "0" * 64
    )
    with pytest.raises(ExtractionValidationError, match="test support partition drifted"):
        validate(_write_manifest(tmp_path, manifest))


def test_integration_tests_cannot_be_hidden_in_research(tmp_path: Path):
    manifest = _manifest()
    manifest["support_partition"]["integration_destination"] = "strategy_research"
    with pytest.raises(
        ExtractionValidationError,
        match="integration tests must remain in the source repository",
    ):
        validate(_write_manifest(tmp_path, manifest))


def test_full_import_names_distinguish_shared_contracts_from_product_data():
    modules = _imported_modules(
        "from data import financial_primitives, macro_data\n"
        "from data.price_target_data import fetch_price_targets\n",
        "synthetic_test.py",
    )
    assert modules >= {
        "data.financial_primitives",
        "data.macro_data",
        "data.price_target_data",
    }
