from __future__ import annotations

import dataclasses
import hashlib
import inspect
import json

import pytest

from research.analyst_revisions_v2_qc import formal_input_composer as module
from research.analyst_revisions_v2_qc.formal_run_protocol import (
    ArtifactBinding,
    TerminalCensusBinding,
)


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _terminal_fixture():
    rows = [
        {
            "schema": module.TERMINAL_OBJECT_SCHEMA,
            "slot_kind": "decision_horizon",
            "slot_id": "decision-1",
            "horizon": 20,
            "disposition": "terminal_payoff",
            "stock_return": "-1",
            "reason": None,
            "terminal_lineage_sha256": "1" * 64,
            "available_at_utc": "2021-01-04T14:00:00Z",
        },
        {
            "schema": module.TERMINAL_OBJECT_SCHEMA,
            "slot_kind": "economic_daily",
            "slot_id": "requirement-1",
            "horizon": None,
            "disposition": "benchmark_splice_continuation",
            "stock_return": None,
            "reason": None,
            "terminal_lineage_sha256": "2" * 64,
            "available_at_utc": "2021-01-05T14:00:00Z",
        },
        {
            "schema": module.TERMINAL_OBJECT_SCHEMA,
            "slot_kind": "economic_daily",
            "slot_id": "requirement-2",
            "horizon": None,
            "disposition": "named_terminal_refusal",
            "stock_return": None,
            "reason": "terminal_payoff_unresolved",
            "terminal_lineage_sha256": "3" * 64,
            "available_at_utc": "2021-01-05T14:00:00Z",
        },
    ]
    rows.sort(key=lambda item: (item["slot_kind"], item["slot_id"], item["horizon"] or 0))
    payload = _canonical(
        {
            "schema": module.TERMINAL_PACKAGE_SCHEMA,
            "terminal_policy_id": "arv2-terminal-payoff-benchmark-splice-v1",
            "row_count": len(rows),
            "rows": rows,
        }
    )
    digest = hashlib.sha256(payload).hexdigest()
    binding = TerminalCensusBinding(
        census=ArtifactBinding(
            artifact_id="terminal-census-artifact",
            content_sha256=digest,
            artifact_sha256="4" * 64,
            byte_count=len(payload),
        ),
        terminal_policy_id="arv2-terminal-payoff-benchmark-splice-v1",
        security_count=2,
        lifecycle_coverage_count=2,
        terminal_requirement_count=3,
        terminal_payoff_count=1,
        benchmark_splice_continuation_count=1,
        named_terminal_refusal_count=1,
        silently_omitted_count=0,
    )
    return payload, binding


def test_terminal_package_authenticates_exact_bytes_and_separate_splice_count():
    payload, binding = _terminal_fixture()
    package = module.load_formal_terminal_disposition_package(
        payload=payload, terminal_census=binding
    )

    assert package.package_sha256 == hashlib.sha256(payload).hexdigest()
    assert package.terminal_payoff_count == 1
    assert package.benchmark_splice_continuation_count == 1
    assert package.named_terminal_refusal_count == 1
    assert package.production_truth_authenticated is False
    assert module.render_formal_terminal_disposition_package_bytes(package) == payload


def test_terminal_package_rejects_equal_value_topology_replacement_and_copy():
    payload, binding = _terminal_fixture()
    package = module.load_formal_terminal_disposition_package(
        payload=payload, terminal_census=binding
    )
    object.__setattr__(package, "rows", tuple([*package.rows]))
    with pytest.raises(module.FormalInputComposerError, match="topology"):
        module.require_formal_terminal_disposition_package(package)

    original = module.load_formal_terminal_disposition_package(
        payload=payload, terminal_census=binding
    )
    copied = object.__new__(module.FormalTerminalDispositionPackage)
    for field in dataclasses.fields(module.FormalTerminalDispositionPackage):
        object.__setattr__(copied, field.name, getattr(original, field.name))
    with pytest.raises(module.FormalInputComposerError, match="loader-authenticated"):
        module.require_formal_terminal_disposition_package(copied)


def test_terminal_package_rejects_census_or_bytes_laundering():
    payload, binding = _terminal_fixture()
    changed = json.loads(payload)
    changed["rows"][0]["disposition"] = "named_terminal_refusal"
    changed["rows"][0]["stock_return"] = None
    changed["rows"][0]["reason"] = "terminal_payoff_unresolved"
    with pytest.raises(module.FormalInputComposerError, match="census binding"):
        module.load_formal_terminal_disposition_package(
            payload=_canonical(changed), terminal_census=binding
        )


def test_production_truth_has_no_public_content_only_mint():
    assert "build_formal_production_truth_authority" not in module.__all__
    assert not hasattr(module, "FormalProductionTruthAuthorityBinding")
    assert "production_truth" in inspect.signature(
        module.build_formal_compact_input_candidate
    ).parameters


def test_zero_actual_terminal_rows_are_a_valid_exact_subset():
    payload = _canonical({
        "schema": module.TERMINAL_PACKAGE_SCHEMA,
        "terminal_policy_id": "arv2-terminal-payoff-benchmark-splice-v1",
        "row_count": 0,
        "rows": [],
    })
    binding = TerminalCensusBinding(
        census=ArtifactBinding(
            artifact_id="terminal-census-empty",
            content_sha256=hashlib.sha256(payload).hexdigest(),
            artifact_sha256="5" * 64,
            byte_count=len(payload),
        ),
        terminal_policy_id="arv2-terminal-payoff-benchmark-splice-v1",
        security_count=2,
        lifecycle_coverage_count=2,
        terminal_requirement_count=0,
        terminal_payoff_count=0,
        benchmark_splice_continuation_count=0,
        named_terminal_refusal_count=0,
        silently_omitted_count=0,
    )
    package = module.load_formal_terminal_disposition_package(
        payload=payload, terminal_census=binding
    )
    assert package.rows == ()
    assert package.production_truth_authenticated is False


def test_legacy_six_result_candidate_cannot_finalize_or_reach_plan_builders(
    monkeypatch,
):
    calls: list[str] = []

    def accept_legacy_candidate(value):
        calls.append("candidate")
        return value

    def forbidden(*args, **kwargs):
        calls.append("downstream")
        raise AssertionError("legacy finalizer reached a downstream plan builder")

    monkeypatch.setattr(
        module, "require_formal_compact_input_candidate", accept_legacy_candidate
    )
    for name in (
        "require_formal_qc_runtime_capacity_binding",
        "build_formal_qc_input_manifest_bytes",
        "build_formal_qc_runtime_projection",
        "build_qc_object_payload_binding",
        "build_formal_qc_upload_bundle",
        "build_formal_run_candidate",
    ):
        monkeypatch.setattr(module, name, forbidden)

    with pytest.raises(
        module.FormalInputComposerError,
        match="legacy six-result compact candidate cannot be finalized",
    ):
        module.finalize_formal_compact_run_plan(
            candidate=object(), capacity=object()
        )

    assert calls == ["candidate"]
    fields = {item.name for item in dataclasses.fields(module.FormalCompactRunPlan)}
    assert "representative_full_census_capacity_verified" not in fields
    assert "downstream_runtime_resource_census_capacity_verified" in fields
    assert (
        "upstream_truth_and_six_result_materialization_capacity_authenticated"
        in fields
    )
