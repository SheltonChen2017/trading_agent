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


def test_second_extraction_dry_run_is_exact_and_not_authorized():
    result = validate()
    assert result["status"] == (
        "valid-second-dry-run-not-ready-for-physical-extraction"
    )
    assert result["source_commit"] == "b15aac8e176bb892f4fb3bd8da87f3eaac66af80"
    assert result["inventory"] == {
        "tracked_paths": 743,
        "sha256": "32590d8bb3d44e67ee90dd0008e2c73cc2356a5004b0484ab7ba908c25d32282",
        "assigned_exactly_once": True,
        "destination_counts": {
            # SEP3R-002: this dict briefly carried both `"shared_contracts": 3`
            # and `"shared_contracts": 4`; Python keeps the later duplicate
            # key silently, so the stale 3 was dead text masking an
            # incomplete edit rather than a failing assertion.
            "shared_contracts": 4,
            "strategy_research": 241,
            "trading_assistant": 498,
        },
    }
    assert result["physical_extraction_authorized"] is False
    assert result["surfaces"]["script_ownership_counts"] == {
        "trading_assistant": 9,
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
        "governance_support_partition": "pending",
        # SEP3R-001: the partition strands ten assistant-needed data modules
        # in the research repository; see the dedicated test below.
        "stranded_data_modules": _STRANDED_DATA_MODULES,
    }
    assert result["surfaces"]["shared_contract_test_files"] == 1


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
    source = manifest["source"]["candidate_commit"]
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


_STRANDED_DATA_MODULES = [
    "data.filing_extraction",
    "data.macro_data",
    "data.mandate_evaluation",
    "data.market_data",
    "data.operational_alerts",
    "data.portfolio_mandate",
    "data.portfolio_metrics",
    "data.price_target_data",
    "data.research_statistics",
    "data.runtime_identity",
]


def test_stranded_data_modules_are_measured_declared_and_blocking():
    """SEP3R-001. The declared partition must not strand a product's imports.

    Both dry runs destined these ten ``data`` modules to the research
    repository while trading-assistant packages or assistant-owned scripts
    import them — `data.mandate_evaluation` and `data.portfolio_mandate` carry
    the owner-approved mandate fingerprint, `data.runtime_identity` the
    evidence lineage, `data.operational_alerts` the alert writer. Executed as
    declared, extraction would break the assistant at import time or force the
    cross-repository dependency the plan's objective forbids. The validator
    now measures the stranded set from the candidate commit; this pins it as
    an exact shrinking blocker rather than a silent pass.
    """
    result = validate()
    assert result["blockers"]["stranded_data_modules"] == _STRANDED_DATA_MODULES
    assert "data.mandate_evaluation" in result["blockers"]["stranded_data_modules"]
    assert result["physical_extraction_authorized"] is False


def test_missing_stranded_declaration_is_refused(tmp_path: Path):
    manifest = _manifest()
    manifest["known_blockers"]["stranded_data_modules"] = (
        _STRANDED_DATA_MODULES[:-1]
    )
    with pytest.raises(
        ExtractionValidationError,
        match="stale extraction blocker stranded_data_modules",
    ):
        validate(_write_manifest(tmp_path, manifest))


def test_overdeclared_stranded_module_is_refused(tmp_path: Path):
    """A blocker list padded with a resolved entry must fail, so the ledger
    is driven down by fixing modules, never by editing the declaration."""
    manifest = _manifest()
    manifest["known_blockers"]["stranded_data_modules"] = (
        _STRANDED_DATA_MODULES + ["data.evidence_status"]
    )
    with pytest.raises(
        ExtractionValidationError,
        match="stale extraction blocker stranded_data_modules",
    ):
        validate(_write_manifest(tmp_path, manifest))
