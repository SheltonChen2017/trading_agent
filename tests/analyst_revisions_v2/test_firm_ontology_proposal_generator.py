"""Focused offline tests for non-authorizing firm-ontology proposals."""
from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from research.analyst_revisions_v2.canonical import canonical_json_bytes
from research.analyst_revisions_v2_qc import firm_ontology_proposal_generator as module
from research.analyst_revisions_v2_qc.firm_ontology_proposal_generator import (
    FirmOntologyProposalCapacityError,
    FirmOntologyProposalError,
    build_firm_ontology_proposal,
    iter_firm_ontology_proposal_firms,
    require_firm_ontology_proposal,
)
from research.analyst_revisions_v2_qc.physical_firm_ontology_review_packet import (
    _build_physical_firm_ontology_review_packet_for_test,
)
from scripts import build_arv2_firm_ontology_proposal as cli
from tests.analyst_revisions_v2.test_physical_firm_ontology_review_packet import (
    _c1,
    _rating,
)


def _packet(tmp_path: Path, extras=(), *, firm_count: int = 74):
    ratings = [
        _rating(
            f"base-{ordinal:03d}",
            firm_id=f"firm-{ordinal:03d}",
            firm_name=f"Firm {ordinal:03d}",
            action="upgrades",
            rating="Buy",
            previous_rating="Hold",
        )
        for ordinal in range(firm_count)
    ]
    ratings.extend(extras)
    c1 = _c1(tmp_path / "source", ratings)
    packet = _build_physical_firm_ontology_review_packet_for_test(
        accepted_risk_archive=c1,
        output_root=tmp_path / "packet",
    )
    return c1, packet


def _raw(artifact) -> dict[str, object]:
    return json.loads(artifact.path.read_text(encoding="utf-8"))


def test_bulk_default_is_deterministic_compact_and_never_self_promotes(
    tmp_path: Path,
) -> None:
    _c1_value, packet = _packet(tmp_path / "one")
    first = build_firm_ontology_proposal(
        review_packet=packet, output_root=tmp_path / "proposal-one"
    )
    second = build_firm_ontology_proposal(
        review_packet=packet, output_root=tmp_path / "proposal-two"
    )
    raw = _raw(first)

    assert require_firm_ontology_proposal(first) is first
    assert first.proposal_id == second.proposal_id
    assert first.proposal_sha256 == second.proposal_sha256
    assert first.payload_sha256 == second.payload_sha256
    assert first.path.read_bytes() == second.path.read_bytes()
    assert first.firm_count == 74
    assert first.bulk_ratification_eligible_firm_count == 74
    assert first.exception_firm_count == 0
    assert first.proposed_primary_mapping_count == 148
    assert first.proposed_alias_mapping_count == 0
    assert first.unresolved_label_count == 0
    assert raw["source"]["mapped_alias_count"] == 39
    assert raw["source"]["measured_refusal_count"] == 15
    assert raw["remaining_owner_choices"]
    assert raw["exception_census"] == []
    assert all(raw[name] is False for name in module.NON_AUTHORITY_FIELDS)

    firm = raw["firms"][0]
    defaults = firm["proposed_defaults"]
    assert defaults["canonical_firm_name"] == "Firm 000"
    assert defaults["validity_intervals"] == [
        {
            "valid_from": "2021-01-04",
            "valid_to": None,
            "owner_confirmation_required": True,
        }
    ]
    assert defaults["scope"] == "company_relative"
    assert [
        (item["raw_label"], item["proposed_ordered_rank"], item["global_legacy_level"])
        for item in defaults["ordered_scale"]
    ] == [("Hold", 1, 3), ("Buy", 2, 4)]
    assert defaults["owner_reviewed_complete"] is False
    for mapping in defaults["ordered_scale"]:
        evidence = mapping["mapping_evidence"]
        seed = dict(evidence)
        seed["evidence_id"] = None
        seed["evidence_sha256"] = None
        assert evidence["evidence_sha256"] == hashlib.sha256(
            canonical_json_bytes(seed)
        ).hexdigest()
        assert evidence["packet_id"] == packet.packet_id
        assert evidence["packet_sha256"] == packet.packet_sha256
        assert evidence["provider_firm_id"] == firm["provider_firm_id"]
        assert evidence["raw_label"] == mapping["raw_label"]
        assert evidence["firm_evidence_row_sha256"] == firm[
            "firm_evidence_row_sha256"
        ]
        assert evidence["evidence_id"] == (
            f"arv2-firm-proposal-evidence-{evidence['evidence_sha256'][:24]}"
        )


def test_full_packet_evidence_census_is_exhausted_but_only_top_74_are_retained(
    tmp_path: Path,
) -> None:
    _c1_value, packet = _packet(tmp_path, firm_count=80)
    artifact = build_firm_ontology_proposal(
        review_packet=packet, output_root=tmp_path / "proposal"
    )
    firms = list(iter_firm_ontology_proposal_firms(artifact))
    assert packet.firm_count == 80
    assert len(firms) == 74
    assert [item["provider_firm_id"] for item in firms] == [
        f"firm-{ordinal:03d}" for ordinal in range(74)
    ]


def test_compose_refuses_a_truncated_evidence_iterator_even_after_all_74_selected(
    monkeypatch,
) -> None:
    templates = [
        {
            "ranking_ordinal": ordinal,
            "provider_firm_id": f"firm-{ordinal - 1:03d}",
            "predeclared_2021_2025_volume_count": 1,
            "observed_firm_names": [f"Firm {ordinal - 1:03d}"],
            "ontology_authority_created": False,
            "availability_authority_created": False,
            "production_authority": False,
        }
        for ordinal in range(1, module.EXPECTED_FIRM_COUNT + 1)
    ]
    evidence = [
        {"provider_firm_id": f"firm-{ordinal:03d}"}
        for ordinal in range(module.EXPECTED_FIRM_COUNT)
    ]
    packet = SimpleNamespace(
        firm_count=80,
        packet_id="packet-id",
        packet_sha256="0" * 64,
        files=(),
    )

    def propose(*, template, **_kwargs):
        return {
            "ranking_ordinal": template["ranking_ordinal"],
            "provider_firm_id": template["provider_firm_id"],
            "proposed_defaults": {
                "owner_reviewed_complete": False,
                "ordered_scale": [],
                "alias_mappings": [],
            },
            "unresolved_labels": [],
            "bulk_ratification_eligible": True,
            "exception_reasons": [],
        }

    monkeypatch.setattr(module, "_PINNED_TEMPLATE_ITERATOR", lambda _packet: templates)
    monkeypatch.setattr(module, "_PINNED_EVIDENCE_ITERATOR", lambda _packet: evidence)
    monkeypatch.setattr(module, "_propose_firm", propose)
    with pytest.raises(FirmOntologyProposalError, match="did not exhaust"):
        module._compose_proposal(packet, module._load_global_map())


def test_propose_firm_refuses_cross_firm_evidence_before_parsing_it() -> None:
    packet = SimpleNamespace(packet_id="packet-id", packet_sha256="0" * 64)
    with pytest.raises(FirmOntologyProposalError, match="evidence/template firm binding"):
        module._propose_firm(
            packet=packet,
            contract=module._load_global_map(),
            template={"provider_firm_id": "firm-a"},
            evidence={"provider_firm_id": "firm-b"},
            resolver_cache={},
        )


@pytest.mark.parametrize(
    "changed_field", ["ranking_type", "ordinal", "volume", "selected", "names"]
)
def test_propose_firm_reauthenticates_template_selection_metadata(
    tmp_path: Path,
    changed_field: str,
) -> None:
    _c1_value, packet = _packet(tmp_path)
    template = deepcopy(next(module._PINNED_TEMPLATE_ITERATOR(packet)))
    evidence = deepcopy(next(module._PINNED_EVIDENCE_ITERATOR(packet)))
    if changed_field == "ranking_type":
        evidence["predeclared_2021_2025_volume_ranking"] = None
    elif changed_field == "ordinal":
        template["ranking_ordinal"] += 1
    elif changed_field == "volume":
        template["predeclared_2021_2025_volume_count"] += 1
    elif changed_field == "selected":
        evidence["predeclared_2021_2025_volume_ranking"][
            "selected_for_owner_adjudication"
        ] = False
    else:
        template["observed_firm_names"].append("Unobserved Name")

    with pytest.raises(
        FirmOntologyProposalError, match="evidence/template selection binding"
    ):
        module._propose_firm(
            packet=packet,
            contract=module._load_global_map(),
            template=template,
            evidence=evidence,
            resolver_cache={},
        )


def test_ambiguous_refused_and_unknown_labels_remain_visible_exceptions(
    tmp_path: Path,
) -> None:
    extras = [
        _rating(
            "ambiguous",
            firm_id="firm-000",
            firm_name="Firm 000",
            action="maintains",
            rating="Top Pick",
            previous_rating="Top Pick",
        ),
        _rating(
            "refused",
            firm_id="firm-000",
            firm_name="Firm 000",
            action="maintains",
            rating="Not Rated",
            previous_rating="Not Rated",
        ),
        _rating(
            "unknown",
            firm_id="firm-000",
            firm_name="Firm 000",
            action="maintains",
            rating="Moonshot",
            previous_rating="Moonshot",
        ),
    ]
    _c1_value, packet = _packet(tmp_path, extras)
    artifact = build_firm_ontology_proposal(
        review_packet=packet, output_root=tmp_path / "proposal"
    )
    firm = _raw(artifact)["firms"][0]
    unresolved = {item["raw_label"]: item for item in firm["unresolved_labels"]}
    assert unresolved["Top Pick"]["reasons"] == [
        "global_map_named_ambiguous_alias"
    ]
    assert unresolved["Not Rated"]["reasons"] == ["frozen_global_refusal"]
    assert unresolved["Moonshot"]["reasons"] == [
        "unknown_or_invalid_global_label"
    ]
    assert all(item["proposed_rank"] is None for item in unresolved.values())
    assert firm["bulk_ratification_eligible"] is False
    assert _raw(artifact)["exception_census"][0] == {
        "ranking_ordinal": 1,
        "provider_firm_id": "firm-000",
        "unresolved_label_count": 3,
        "reasons": [
            "frozen_global_refusal",
            "global_map_named_ambiguous_alias",
            "unknown_or_invalid_global_label",
        ],
    }


def test_cycles_opposite_directions_and_tier_collapses_are_not_guessed(
    tmp_path: Path,
) -> None:
    extras = [
        _rating(
            "opposite",
            firm_id="firm-000",
            firm_name="Firm 000",
            action="downgrades",
            rating="Buy",
            previous_rating="Hold",
        ),
        _rating(
            "collapse",
            firm_id="firm-001",
            firm_name="Firm 001",
            action="upgrades",
            rating="Neutral",
            previous_rating="Hold",
        ),
    ]
    _c1_value, packet = _packet(tmp_path, extras)
    artifact = build_firm_ontology_proposal(
        review_packet=packet, output_root=tmp_path / "proposal"
    )
    firms = _raw(artifact)["firms"]
    first = {item["raw_label"]: item for item in firms[0]["unresolved_labels"]}
    assert "firm_directional_cycle" in first["Buy"]["reasons"]
    assert "firm_global_opposite_direction" in first["Buy"]["reasons"]
    assert "firm_directional_cycle" in first["Hold"]["reasons"]
    second = {item["raw_label"]: item for item in firms[1]["unresolved_labels"]}
    assert second["Hold"]["reasons"] == ["firm_global_tier_collapse"]
    assert second["Neutral"]["reasons"] == ["firm_global_tier_collapse"]
    assert firms[0]["bulk_ratification_eligible"] is False
    assert firms[1]["bulk_ratification_eligible"] is False


def test_private_output_tamper_and_forgery_are_refused(tmp_path: Path) -> None:
    _c1_value, packet = _packet(tmp_path)
    artifact = build_firm_ontology_proposal(
        review_packet=packet, output_root=tmp_path / "proposal"
    )
    artifact.path.write_bytes(artifact.path.read_bytes() + b"{}\n")
    with pytest.raises(FirmOntologyProposalError, match="identity changed"):
        require_firm_ontology_proposal(artifact)


def test_private_output_tolerates_noncontent_extended_metadata(
    tmp_path: Path,
) -> None:
    """macOS provenance must not invalidate content-identical owner evidence."""

    _c1_value, packet = _packet(tmp_path)
    artifact = build_firm_ontology_proposal(
        review_packet=packet, output_root=tmp_path / "proposal"
    )
    before = artifact.path.stat(follow_symlinks=False)
    if sys.platform == "darwin":
        completed = subprocess.run(
            [
                "/usr/bin/xattr",
                "-w",
                "com.openai.arv2-test",
                "content-identical",
                str(artifact.path),
            ],
            check=False,
            capture_output=True,
        )
        if completed.returncode:
            pytest.skip("test filesystem rejected extended attributes")
    elif hasattr(os, "setxattr"):
        try:
            os.setxattr(artifact.path, "user.arv2-test", b"content-identical")
        except OSError as exc:
            pytest.skip(f"test filesystem rejected extended attributes: {exc}")
    else:
        pytest.skip("extended attributes are unavailable")
    after = artifact.path.stat(follow_symlinks=False)

    assert after.st_ctime_ns != before.st_ctime_ns
    assert after.st_mtime_ns == before.st_mtime_ns
    assert require_firm_ontology_proposal(artifact) is artifact


def test_nested_self_promotion_and_rebound_composer_are_isolated(
    tmp_path: Path, monkeypatch
) -> None:
    _c1_value, packet = _packet(tmp_path)
    contract = module._load_global_map()
    proposal, counts = module._compose_proposal(packet, contract)
    promoted = deepcopy(proposal)
    promoted["firms"][0]["proposed_defaults"]["owner_reviewed_complete"] = True
    with pytest.raises(FirmOntologyProposalError, match="nested non-authority"):
        module._require_non_authorizing_proposal(
            promoted, expected_counts=counts
        )

    called = 0

    def hostile_composer(**_kwargs):
        nonlocal called
        called += 1
        raise AssertionError("hostile composer was reached")

    monkeypatch.setattr(module, "_propose_firm", hostile_composer)
    with pytest.raises(FirmOntologyProposalError, match="dependency authority"):
        build_firm_ontology_proposal(
            review_packet=packet, output_root=tmp_path / "proposal"
        )
    assert called == 0
    assert not (tmp_path / "proposal").exists()


def test_capacity_guards_are_isolated_before_output(tmp_path: Path, monkeypatch) -> None:
    with pytest.raises(FirmOntologyProposalCapacityError, match="observed-label"):
        module._observed_labels(
            {"observed_labels": [{}] * (module.MAX_LABELS_PER_FIRM + 1)}
        )
    with pytest.raises(FirmOntologyProposalCapacityError, match="transition census"):
        module._transition_conflicts(
            {
                "transition_counts": [
                    {}
                    for _ in range(module.MAX_TRANSITIONS_PER_FIRM + 1)
                ]
            },
            {},
            {},
        )

    _c1_value, packet = _packet(tmp_path)
    monkeypatch.setattr(module, "MAX_PROPOSAL_BYTES", 100)
    with pytest.raises(FirmOntologyProposalCapacityError, match="byte bound"):
        build_firm_ontology_proposal(
            review_packet=packet, output_root=tmp_path / "proposal"
        )
    assert not (tmp_path / "proposal").exists()


def test_private_write_failure_cleans_only_its_fresh_output(tmp_path: Path, monkeypatch) -> None:
    _c1_value, packet = _packet(tmp_path)

    def fail_write(_descriptor, _payload):
        raise OSError("injected write failure")

    monkeypatch.setattr(module.os, "write", fail_write)
    with pytest.raises(FirmOntologyProposalError, match="private writer failed"):
        build_firm_ontology_proposal(
            review_packet=packet, output_root=tmp_path / "proposal"
        )
    assert not (tmp_path / "proposal").exists()


def test_creator_pid_and_fork_inheritance_are_refused(
    tmp_path: Path, monkeypatch
) -> None:
    _c1_value, packet = _packet(tmp_path)
    artifact = build_firm_ontology_proposal(
        review_packet=packet, output_root=tmp_path / "proposal"
    )
    monkeypatch.setattr(module, "_AUTHORITY_PID", os.getpid() + 1)
    with pytest.raises(FirmOntologyProposalError, match="current process"):
        require_firm_ontology_proposal(artifact)
    monkeypatch.undo()
    if not hasattr(os, "fork"):
        return
    read_descriptor, write_descriptor = os.pipe()
    child = os.fork()
    if child == 0:
        os.close(read_descriptor)
        reset = module._AUTHORITY_PID == os.getpid() and module._AUTHORITIES == {}
        try:
            require_firm_ontology_proposal(artifact)
        except FirmOntologyProposalError:
            refused = True
        else:
            refused = False
        os.write(write_descriptor, b"ok" if reset and refused else b"bad")
        os.close(write_descriptor)
        os._exit(0)
    os.close(write_descriptor)
    try:
        result = os.read(read_descriptor, 3)
    finally:
        os.close(read_descriptor)
    waited, status = os.waitpid(child, 0)
    assert waited == child and os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0
    assert result == b"ok"
    assert require_firm_ontology_proposal(artifact) is artifact


def test_source_has_no_candidate_promotion_or_external_action_surface() -> None:
    source = Path(module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert not any(
        name == prefix or name.startswith(prefix + ".")
        for name in imported
        for prefix in (
            "requests",
            "urllib",
            "socket",
            "quantconnect",
            "research.analyst_revisions_v2.firm_ontology",
            "research.analyst_revisions_v2_qc.firm_ontology_candidate_builder",
            "research.analyst_revisions_v2_qc.production_evidence_composer",
        )
    )
    forbidden = {
        "create_project",
        "compile_project",
        "backtest",
        "launch",
        "history",
        "build_firm_ontology_candidate_bundle",
        "publish_firm_ontology_candidate_bundle",
        "register",
        "submit_order",
    }
    assert not {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    } & forbidden


def test_cli_routes_only_external_pins_to_reloaders_and_proposal_builder(
    tmp_path: Path,
) -> None:
    c1, packet = _packet(tmp_path / "inputs")
    calls: list[tuple[str, dict[str, object]]] = []

    def c1_loader(**kwargs):
        calls.append(("c1", kwargs))
        return c1

    def packet_loader(**kwargs):
        calls.append(("packet", kwargs))
        return packet

    summary = cli._run(
        massive_source_artifact=c1.source_artifact_path,
        massive_source_manifest_sha256=c1.source_manifest_sha256,
        accepted_risk_archive=c1.archive_path,
        accepted_risk_archive_sha256=c1.archive_sha256,
        firm_review_packet=packet.archive_path,
        firm_review_packet_sha256=packet.packet_sha256,
        proposal_output_root=tmp_path / "proposal",
        c1_loader=c1_loader,
        packet_loader=packet_loader,
    )

    assert calls == [
        (
            "c1",
            {
                "archive_path": c1.archive_path,
                "source_artifact_path": c1.source_artifact_path,
                "expected_archive_sha256": c1.archive_sha256,
                "expected_source_manifest_sha256": c1.source_manifest_sha256,
            },
        ),
        (
            "packet",
            {
                "archive_path": packet.archive_path,
                "expected_packet_sha256": packet.packet_sha256,
                "accepted_risk_archive": c1,
            },
        ),
    ]
    assert summary["status"] == (
        "owner_ratification_and_exception_adjudication_required"
    )
    assert all(summary[name] is False for name in module.NON_AUTHORITY_FIELDS)
    assert summary["firm_count"] == 74
    assert summary["bulk_ratification_eligible_firm_count"] == 74
    assert summary["exception_firm_count"] == 0
    assert summary["owner_reviewed_complete"] is False
    assert summary["production_authority"] is False
    assert summary["credential_access"] is False
    assert summary["result_access"] is False
