"""Offline tests for the one-process firm-candidate CLI orchestration."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from research.analyst_revisions_v2_qc.physical_firm_ontology_review_packet import (
    _build_physical_firm_ontology_review_packet_for_test,
)
from scripts import build_arv2_firm_ontology_candidates as cli
from tests.analyst_revisions_v2.test_firm_ontology_candidate_builder import (
    _owner_rows,
    _write_owner,
)
from tests.analyst_revisions_v2.test_physical_firm_ontology_review_packet import (
    _c1,
    _rating,
)


def _inputs(tmp_path: Path):
    ratings = [
        _rating(
            f"rating-{ordinal:03d}",
            firm_id=f"firm-{ordinal:03d}",
            firm_name=f"Firm {ordinal:03d}",
            action="upgrades",
            rating="Buy",
            previous_rating="Hold",
        )
        for ordinal in range(74)
    ]
    c1 = _c1(tmp_path / "initial", ratings)
    packet = _build_physical_firm_ontology_review_packet_for_test(
        accepted_risk_archive=c1,
        output_root=tmp_path / "initial-packet",
    )
    owner = _write_owner(tmp_path / "owner.jsonl", _owner_rows(packet))
    return c1, packet, owner


def test_one_process_chain_reloads_packet_and_publishes_safe_summary(
    tmp_path: Path,
) -> None:
    c1, original_packet, owner = _inputs(tmp_path)
    candidate_output = tmp_path / "fresh-candidates"
    c1_calls = []
    packet_calls = []

    def reuse_test_authority(**kwargs):
        c1_calls.append(kwargs)
        return c1

    def reuse_test_packet(**kwargs):
        packet_calls.append(kwargs)
        return original_packet

    summary = cli._run(
        massive_source_artifact=c1.source_artifact_path,
        massive_source_manifest_sha256=c1.source_manifest_sha256,
        accepted_risk_archive=c1.archive_path,
        accepted_risk_archive_sha256=c1.archive_sha256,
        firm_review_packet=original_packet.archive_path,
        firm_review_packet_sha256=original_packet.packet_sha256,
        owner_adjudication_file=owner,
        candidate_output_root=candidate_output,
        c1_loader=reuse_test_authority,
        packet_loader=reuse_test_packet,
    )

    assert c1_calls == [
        {
            "archive_path": c1.archive_path,
            "source_artifact_path": c1.source_artifact_path,
            "expected_archive_sha256": c1.archive_sha256,
            "expected_source_manifest_sha256": c1.source_manifest_sha256,
        }
    ]
    assert packet_calls == [
        {
            "archive_path": original_packet.archive_path,
            "expected_packet_sha256": original_packet.packet_sha256,
            "accepted_risk_archive": c1,
        }
    ]
    assert summary["status"] == "candidate_archive_published_not_authorized"
    assert summary["firm_review_packet_id"] == original_packet.packet_id
    assert summary["firm_count"] == 74
    assert summary["ontology_entry_count"] == 222
    assert summary["full_massive_capture_rebuilt_once"] is False
    assert summary["firm_review_source_rows_retraversed_once"] is False
    assert summary["trusted_physical_packet_disk_reload_used"] is True
    assert summary["independently_reviewed"] is False
    assert summary["production_authority"] is False
    assert candidate_output.is_dir()
    archive_path = Path(summary["candidate_archive_path"])
    assert archive_path.parent == candidate_output
    assert archive_path.is_dir()


@pytest.mark.parametrize(
    "mutation",
    ("existing-output", "nested-output", "relative-output", "symlink-input"),
)
def test_preflight_refuses_ambiguous_or_reused_paths_before_any_build(
    tmp_path: Path, mutation: str
) -> None:
    c1, _packet, owner = _inputs(tmp_path)
    accepted = c1.archive_path
    packet = _packet.archive_path
    candidate = tmp_path / "candidate"
    source = c1.source_artifact_path
    if mutation == "existing-output":
        candidate.mkdir()
    elif mutation == "nested-output":
        candidate = accepted / "nested"
    elif mutation == "relative-output":
        candidate = Path("relative-candidate")
    else:
        alias = tmp_path / "source-alias"
        alias.symlink_to(source, target_is_directory=True)
        source = alias
    called = False

    def must_not_build(**_kwargs):
        nonlocal called
        called = True
        raise AssertionError("preflight failed to stop before C1")

    with pytest.raises(ValueError):
        if mutation == "relative-output":
            cli._absolute(str(candidate), "candidate output root")
        else:
            cli._run(
                massive_source_artifact=source,
                massive_source_manifest_sha256=c1.source_manifest_sha256,
                accepted_risk_archive=accepted,
                accepted_risk_archive_sha256=c1.archive_sha256,
                firm_review_packet=packet,
                firm_review_packet_sha256=_packet.packet_sha256,
                owner_adjudication_file=owner,
                candidate_output_root=candidate,
                c1_loader=must_not_build,
            )
    assert called is False


def test_cli_source_has_no_network_qc_outcome_or_registry_write_surface() -> None:
    source = Path(cli.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert not any(
        imported == prefix or imported.startswith(prefix + ".")
        for imported in imports
        for prefix in ("requests", "urllib", "http", "socket", "quantconnect")
    )
    forbidden_calls = {
        "create_project",
        "compile_project",
        "backtest",
        "launch",
        "history",
        "submit_order",
        "write_registry",
    }
    assert not {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    } & forbidden_calls
