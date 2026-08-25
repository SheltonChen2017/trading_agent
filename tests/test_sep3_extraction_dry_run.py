"""Dangerous-direction tests for the current SEP-3 extraction dry run."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import scripts.validate_sep3_extraction as sep3_validator

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


def test_eighth_extraction_dry_run_is_exact_and_not_authorized():
    result = validate()
    assert result["status"] == (
        "valid-eighth-dry-run-not-ready-for-physical-extraction"
    )
    assert result["source_commit"] == "80b9a7ed006210d80f89ff798b4f2477cb027f82"
    assert result["inventory"] == {
        "tracked_paths": 757,
        "sha256": "5916ffcff7e5d86d5aab3aead0d2aa489cc0fdd87476908e2b94208205921b1e",
        "assigned_exactly_once": True,
        "destination_counts": {
            # SEP3R-002: this dict briefly carried both `"shared_contracts": 3`
            # and `"shared_contracts": 4`; Python keeps the later duplicate
            # key silently, so the stale 3 was dead text masking an
            # incomplete edit rather than a failing assertion.
            "shared_contracts": 4,
            "strategy_research": 246,
            "trading_assistant": 507,
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
            "product-and-governance-tests-pinned-integration-explicit"
        ),
        "integration_test_files": 42,
        "governance_support_partition": (
            "non-test-documentation-product-ownership-pending"
        ),
        # SEP3A-001 and SEP3S-001 assign two services without widening the
        # shared package. SEP3RI-001 privately splits runtime identity and
        # SEP3MP-001 privately splits descriptive macro proxies, so six
        # genuinely dual-use data modules remain.
        "stranded_data_modules": _STRANDED_DATA_MODULES,
        "stranded_data_module_importer_sides": _STRANDED_IMPORTER_SIDES,
        "stranded_product_top_level_modules": _STRANDED_TOP_LEVEL_MODULES,
        "stranded_product_top_level_importer_sides": (
            _STRANDED_TOP_LEVEL_IMPORTER_SIDES
        ),
    }
    assert result["surfaces"]["shared_contract_test_files"] == 1
    assert result["surfaces"]["governance_test_files"] == 6
    assert result["surfaces"]["test_counts"] == {
        "trading_assistant": 84,
        "strategy_research": 75,
        "shared_contracts": 1,
        "integration": 42,
        "governance": 6,
    }
    assert result["surfaces"]["test_inventory_sha256"] == {
        "trading_assistant": (
            "f073b27da5b4cfd28bd516b84b47a947848e30cf5215f2eb54d0253bcccaa744"
        ),
        "strategy_research": (
            "236ef9fc29d9023d6fc3a625da1755225446920e5b1e7bf62d4cff09c20a0016"
        ),
        "shared_contracts": (
            "99f98d144d43c92720202126fdff6734a3a310720c18e9f974903b95e8a0f192"
        ),
        "integration": (
            "bf2688760aeb8136b30f625fb0fdbaec62cfafa3f81ff534d0cd7f3ac9b1d0fe"
        ),
        "governance": (
            "7d7bb973104f5c31718293cec1768bd1684b88b5a7a4d6619572ef2df6126fab"
        ),
    }


def test_current_dry_run_review_status_matches_accepted_review_record():
    """CRSEP3ST-002: active status must advance when review is committed.

    A new candidate starts pending. Once a committed independent SEP-3 report
    accepts that exact candidate prefix, the manifest and both active plans
    must stop claiming the same dry run still awaits review. A later candidate
    naturally returns to pending until its own report exists.
    """
    manifest = _manifest()
    candidate_prefix = manifest["source"]["candidate_commit"][:7]
    review_root = DEFAULT_MANIFEST.parents[1] / "docs" / "Archive" / "Review"
    accepted = any(
        candidate_prefix in text
        and ("Verdict: accepted" in text or "**Accepted" in text)
        for path in review_root.glob("REVIEW_*SEP3*.md")
        if (text := path.read_text(encoding="utf-8"))
    )
    expected = "accepted" if accepted else "pending"
    assert manifest["source"]["independent_review_status"] == expected

    separation_plan = (
        DEFAULT_MANIFEST.parents[1]
        / "docs"
        / "PROJECT_SEPARATION_IMPLEMENTATION_PLAN.md"
    ).read_text(encoding="utf-8")
    action_plan = (
        DEFAULT_MANIFEST.parents[1] / "docs" / "ACTION_PLAN_2026-08-20.md"
    ).read_text(encoding="utf-8")
    ordinal = manifest["status"].split("-dry-run", 1)[0]
    if expected == "accepted":
        assert f"{ordinal} dry run pending review" not in separation_plan.lower()
        assert f"{ordinal} dry run awaits independent review" not in action_plan.lower()
    else:
        assert f"{ordinal} dry run pending review" in separation_plan.lower()
        assert f"{ordinal} dry run awaits independent review" in action_plan.lower()


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


def _manifest_with_explicit_test_ownership() -> dict:
    manifest = _manifest()
    manifest["support_partition"]["explicit_test_ownership"] = {
        "trading_assistant": [
            "tests/test_launch_dev_app.py",
            "tests/test_operational_task_resilience.py",
            "tests/test_setup_operational_host.py",
        ],
        "strategy_research": [
            "tests/test_allocation_policy.py",
            "tests/test_leveraged_threshold.py",
            "tests/test_ml_helper_divergence.py",
        ],
        "governance": [
            "tests/conftest.py",
            "tests/test_active_document_consistency.py",
            "tests/test_ml_import_boundary.py",
            "tests/test_overlay_import_boundary.py",
            "tests/test_runtime_artifact_ignores.py",
            "tests/test_schema_version_inventory.py",
        ],
    }
    manifest["support_partition"]["governance_destination"] = (
        "trading_assistant"
    )
    manifest["support_partition"]["governance_test_files"] = 6
    return manifest


def test_explicit_test_ownership_cannot_hide_static_product_imports(
    tmp_path: Path,
):
    manifest = _manifest_with_explicit_test_ownership()
    manifest["support_partition"]["explicit_test_ownership"]["governance"].append(
        "tests/test_research_looks.py"
    )
    with pytest.raises(
        ExtractionValidationError,
        match="cannot override statically measured product imports",
    ):
        validate(_write_manifest(tmp_path, manifest))


def test_explicit_test_ownership_cannot_duplicate_a_path(tmp_path: Path):
    manifest = _manifest_with_explicit_test_ownership()
    manifest["support_partition"]["explicit_test_ownership"][
        "strategy_research"
    ].append("tests/test_launch_dev_app.py")
    with pytest.raises(
        ExtractionValidationError, match="duplicate explicit test ownership"
    ):
        validate(_write_manifest(tmp_path, manifest))


def test_explicit_test_ownership_cannot_name_a_stale_path(tmp_path: Path):
    manifest = _manifest_with_explicit_test_ownership()
    manifest["support_partition"]["explicit_test_ownership"]["governance"].append(
        "tests/test_missing_sep3_support.py"
    )
    with pytest.raises(
        ExtractionValidationError, match="stale explicit test ownership paths"
    ):
        validate(_write_manifest(tmp_path, manifest))


def test_governance_tests_stay_with_source_repository_support(tmp_path: Path):
    manifest = _manifest_with_explicit_test_ownership()
    manifest["support_partition"]["governance_destination"] = (
        "strategy_research"
    )
    with pytest.raises(
        ExtractionValidationError,
        match="governance tests must remain with migration support",
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
    "data.mandate_evaluation",
    "data.market_data",
    "data.portfolio_mandate",
    "data.portfolio_metrics",
    "data.price_target_data",
]

_DUAL_USE_SIDES = ["strategy_research", "trading_assistant"]
_STRANDED_IMPORTER_SIDES = {
    module: _DUAL_USE_SIDES for module in _STRANDED_DATA_MODULES
}

# CRSEP3ST-001: SEP3R-001 measured only data.* assignments. The same
# dangerous direction existed in the separately assigned top-level modules.
# SEP3M-001 removes the assistant's research-owned market_analytics import;
# config remains dual-use on the eighth candidate.
_STRANDED_TOP_LEVEL_MODULES = ["config"]
_STRANDED_TOP_LEVEL_IMPORTER_SIDES = {
    module: _DUAL_USE_SIDES for module in _STRANDED_TOP_LEVEL_MODULES
}


def test_stranded_data_modules_are_measured_declared_and_blocking():
    """SEP3R-001. The declared partition must not strand a product's imports.

    The first two dry runs destined ten assistant-needed modules to research.
    SEP3A-001 assigns the sole assistant-only service, operational alerts, to
    the assistant. SEP3S-001 makes research statistics research-owned and
    removes the assistant import. SEP3RI-001 makes runtime identity research-
    owned and gives the assistant a behavior-identical private implementation.
    SEP3MP-001 makes the macro proxies research-owned and gives the assistant
    behavior-identical private descriptive calculations. The remaining six
    modules are imported by both products, including the mandate-fingerprint
    pair.
    Extraction would still break one product or force the cross-repository
    dependency the plan forbids. The validator measures both set and importer
    sides from the candidate commit, pinning an exact shrinking blocker rather
    than a silent pass.
    """
    result = validate()
    assert result["blockers"]["stranded_data_modules"] == _STRANDED_DATA_MODULES
    assert "data.mandate_evaluation" in result["blockers"]["stranded_data_modules"]
    assert result["blockers"]["stranded_data_module_importer_sides"] == (
        _STRANDED_IMPORTER_SIDES
    )
    assert sum(
        sides == _DUAL_USE_SIDES
        for sides in result["blockers"]["stranded_data_module_importer_sides"].values()
    ) == 6
    assert "data.operational_alerts" not in result["blockers"][
        "stranded_data_modules"
    ]
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


def test_incorrect_stranded_importer_side_is_refused(tmp_path: Path):
    """A dual-use module cannot be presented as a simple reassignment."""
    manifest = _manifest()
    manifest["known_blockers"]["stranded_data_module_importer_sides"][
        "data.price_target_data"
    ] = ["trading_assistant"]
    with pytest.raises(
        ExtractionValidationError,
        match="stale extraction blocker stranded_data_module_importer_sides",
    ):
        validate(_write_manifest(tmp_path, manifest))


def test_product_top_level_crossings_are_measured_declared_and_blocking():
    result = validate()
    assert result["blockers"]["stranded_product_top_level_modules"] == (
        _STRANDED_TOP_LEVEL_MODULES
    )
    assert result["blockers"][
        "stranded_product_top_level_importer_sides"
    ] == _STRANDED_TOP_LEVEL_IMPORTER_SIDES
    assert result["physical_extraction_authorized"] is False


def test_missing_stranded_product_top_level_declaration_is_refused(
    tmp_path: Path,
):
    manifest = _manifest()
    manifest["known_blockers"]["stranded_product_top_level_modules"] = []
    with pytest.raises(
        ExtractionValidationError,
        match="stale extraction blocker stranded_product_top_level_modules",
    ):
        validate(_write_manifest(tmp_path, manifest))


def test_incorrect_product_top_level_importer_side_is_refused(tmp_path: Path):
    manifest = _manifest()
    manifest["known_blockers"][
        "stranded_product_top_level_importer_sides"
    ]["config"] = ["strategy_research"]
    with pytest.raises(
        ExtractionValidationError,
        match=(
            "stale extraction blocker "
            "stranded_product_top_level_importer_sides"
        ),
    ):
        validate(_write_manifest(tmp_path, manifest))


def test_restored_assistant_market_analytics_import_is_refused(monkeypatch):
    """SEP3M-001: the removed product-to-product direction stays closed."""
    original_commit_text = sep3_validator._commit_text

    def with_restored_import(commit: str, path: str) -> str:
        source = original_commit_text(commit, path)
        if path == "assistant/context_builder.py":
            return source + "\nfrom market_analytics import classify_trend\n"
        return source

    monkeypatch.setattr(sep3_validator, "_commit_text", with_restored_import)
    with pytest.raises(
        ExtractionValidationError,
        match="stale extraction blocker stranded_product_top_level_modules",
    ):
        validate()


def test_restored_assistant_runtime_identity_import_is_refused(monkeypatch):
    """SEP3RI-001: the removed assistant-to-research import stays closed."""
    original_commit_text = sep3_validator._commit_text

    def with_restored_import(commit: str, path: str) -> str:
        source = original_commit_text(commit, path)
        if path == "assistant/runtime_identity.py":
            return source + "\nfrom data.runtime_identity import current_commit\n"
        return source

    monkeypatch.setattr(sep3_validator, "_commit_text", with_restored_import)
    with pytest.raises(
        ExtractionValidationError,
        match="stale extraction blocker stranded_data_modules",
    ):
        validate()


def test_restored_assistant_macro_data_import_is_refused(monkeypatch):
    """SEP3MP-001: the removed assistant-to-research import stays closed."""
    original_commit_text = sep3_validator._commit_text

    def with_restored_import(commit: str, path: str) -> str:
        source = original_commit_text(commit, path)
        if path == "assistant/macro_context.py":
            return source + "\nfrom data.macro_data import build_credit_spread_proxy\n"
        return source

    monkeypatch.setattr(sep3_validator, "_commit_text", with_restored_import)
    with pytest.raises(
        ExtractionValidationError,
        match="stale extraction blocker stranded_data_modules",
    ):
        validate()
