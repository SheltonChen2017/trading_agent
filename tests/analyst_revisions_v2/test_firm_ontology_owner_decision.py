"""Focused tests for the mixed deterministic-default/named-refusal artifact."""
from __future__ import annotations

import copy
import dataclasses
import json
import os
import weakref
from pathlib import Path
from types import SimpleNamespace

import pytest

from research.analyst_revisions_v2.canonical import canonical_json_bytes, sha256_bytes
from research.analyst_revisions_v2_qc import firm_ontology_owner_decision as module
from research.analyst_revisions_v2_qc.firm_ontology_owner_decision import (
    FirmOntologyOwnerDecisionArtifact,
    FirmOntologyOwnerDecisionError,
    FirmOntologyOwnerDecisionStatus,
    build_firm_ontology_owner_decision,
    iter_firm_ontology_named_refusals,
    iter_firm_ontology_owner_decisions,
    require_firm_ontology_owner_decision,
)
from research.analyst_revisions_v2_qc.firm_ontology_proposal_generator import (
    build_firm_ontology_proposal,
    iter_firm_ontology_proposal_firms,
)
from tests.analyst_revisions_v2.test_firm_ontology_proposal_generator import (
    _packet,
)
from tests.analyst_revisions_v2.test_physical_firm_ontology_review_packet import (
    _rating,
)


def _exception_rating():
    return _rating(
        "unknown",
        firm_id="firm-000",
        firm_name="Firm 000",
        action="maintains",
        rating="Moonshot",
        previous_rating="Moonshot",
    )


def _build_context(root: Path):
    _c1_value, packet = _packet(root / "input", extras=[_exception_rating()])
    proposal = build_firm_ontology_proposal(
        review_packet=packet,
        output_root=root / "proposal",
    )
    artifact = build_firm_ontology_owner_decision(
        review_packet=packet,
        proposal=proposal,
    )
    proposal_firms = tuple(iter_firm_ontology_proposal_firms(proposal))
    decision = json.loads(artifact.decision_bytes)
    ledger = json.loads(artifact.refusal_ledger_bytes)
    return SimpleNamespace(
        packet=packet,
        proposal=proposal,
        proposal_firms=proposal_firms,
        artifact=artifact,
        decision=decision,
        ledger=ledger,
        source=decision["source"],
    )


@pytest.fixture(scope="module")
def context(tmp_path_factory):
    return _build_context(tmp_path_factory.mktemp("firm-owner-decision"))


def _refresh_entry(entry: dict[str, object]) -> None:
    module._address_record(
        entry,
        identifier_field="refusal_id",
        digest_field="refusal_sha256",
        prefix="arv2-firm-named-refusal-",
    )


def _refresh_documents(
    decision: dict[str, object], ledger: dict[str, object]
) -> None:
    module._address_record(
        ledger,
        identifier_field="ledger_id",
        digest_field="ledger_sha256",
        prefix="arv2-firm-refusal-ledger-",
    )
    decision["refusal_ledger"] = {
        "ledger_id": ledger["ledger_id"],
        "ledger_sha256": ledger["ledger_sha256"],
        "ledger_payload_sha256": sha256_bytes(canonical_json_bytes(ledger)),
    }
    module._address_record(
        decision,
        identifier_field="decision_id",
        digest_field="decision_sha256",
        prefix="arv2-firm-owner-decision-",
    )


def _validate(context, decision, ledger):
    return module._require_documents(
        decision=decision,
        ledger=ledger,
        proposal_firms=context.proposal_firms,
        expected_source=context.source,
    )


def _authorize_test_clone(context, **changes):
    clone = dataclasses.replace(context.artifact, **changes)
    reference = weakref.ref(clone)
    module._AUTHORITIES[id(clone)] = (
        reference,
        module._fingerprint(clone),
        weakref.ref(context.proposal),
        weakref.ref(context.packet),
        os.getpid(),
    )
    return clone


def _forget_test_clone(clone) -> None:
    module._AUTHORITIES.pop(id(clone), None)


def test_mixed_decision_is_deterministic_exact_and_non_authorizing(context):
    second = build_firm_ontology_owner_decision(
        review_packet=context.packet,
        proposal=context.proposal,
    )
    artifact = context.artifact

    assert require_firm_ontology_owner_decision(artifact) is artifact
    assert type(artifact) is FirmOntologyOwnerDecisionArtifact
    assert artifact.decision_id == second.decision_id
    assert artifact.decision_sha256 == second.decision_sha256
    assert artifact.decision_bytes == second.decision_bytes
    assert artifact.refusal_ledger_id == second.refusal_ledger_id
    assert artifact.refusal_ledger_sha256 == second.refusal_ledger_sha256
    assert artifact.refusal_ledger_bytes == second.refusal_ledger_bytes
    assert artifact.firm_count == 74
    assert artifact.accepted_firm_count == 73
    assert artifact.refused_firm_count == 1
    assert artifact.availability_proxy_count == 146
    assert artifact.decision_payload_sha256 == sha256_bytes(
        artifact.decision_bytes
    )
    assert artifact.refusal_ledger_payload_sha256 == sha256_bytes(
        artifact.refusal_ledger_bytes
    )
    assert all(
        getattr(artifact, name) is False for name in module._CAPABILITY_NAMES
    )
    assert context.decision["capabilities"] == {
        name: False for name in module._CAPABILITY_NAMES
    }
    assert context.decision["policy"]["true_historical_availability_claimed"] is False
    assert context.decision["policy"]["independent_production_review_still_required"] is True


def test_clean_firm_copies_only_authenticated_defaults_and_proxy(context):
    proposal_by_id = {
        item["provider_firm_id"]: item for item in context.proposal_firms
    }
    decisions = list(iter_firm_ontology_owner_decisions(context.artifact))
    accepted = next(
        item
        for item in decisions
        if item["decision_status"]
        == FirmOntologyOwnerDecisionStatus.ACCEPTED_DETERMINISTIC_DEFAULT.value
    )
    source = proposal_by_id[accepted["provider_firm_id"]]

    assert accepted["accepted_proposal_defaults"] == source["proposed_defaults"]
    assert accepted["accepted_proposal_defaults_sha256"] == sha256_bytes(
        canonical_json_bytes(source["proposed_defaults"])
    )
    assert accepted["refusal_id"] is None
    assert accepted["refusal_sha256"] is None
    assert len(accepted["availability_proxies"]) == 2
    for proxy in accepted["availability_proxies"]:
        assert proxy["proxy_kind"] == module.AVAILABILITY_PROXY_KIND
        assert proxy["authenticated_first_event_date"] == "2021-01-04"
        assert proxy["proxy_session"] == "2021-01-05"
        assert proxy["proxy_open_at"] == "2021-01-05T14:30:00+00:00"
        assert proxy["historical_availability_claimed"] is False
        assert "available_at" not in proxy
    for mapping in (
        accepted["accepted_proposal_defaults"]["ordered_scale"]
        + accepted["accepted_proposal_defaults"]["alias_mappings"]
    ):
        assert mapping["mapping_evidence"]["availability_time_proposed"] is None


def test_exception_firm_has_no_mappings_and_exact_content_addressed_refusal(context):
    decisions = list(iter_firm_ontology_owner_decisions(context.artifact))
    refused = [
        item
        for item in decisions
        if item["decision_status"]
        == FirmOntologyOwnerDecisionStatus.NAMED_REFUSAL.value
    ]
    ledger = list(iter_firm_ontology_named_refusals(context.artifact))

    assert len(refused) == len(ledger) == 1
    decision = refused[0]
    refusal = ledger[0]
    assert decision["provider_firm_id"] == "firm-000"
    assert decision["accepted_proposal_defaults"] is None
    assert decision["accepted_proposal_defaults_sha256"] is None
    assert decision["availability_proxies"] == []
    assert decision["refusal_id"] == refusal["refusal_id"]
    assert decision["refusal_sha256"] == refusal["refusal_sha256"]
    assert refusal["exception_reasons"] == ["unknown_or_invalid_global_label"]
    assert [item["raw_label"] for item in refusal["unresolved_labels"]] == [
        "Moonshot"
    ]
    assert refusal["unresolved_labels_sha256"] == sha256_bytes(
        canonical_json_bytes(refusal["unresolved_labels"])
    )
    assert refusal["exception_reasons_sha256"] == sha256_bytes(
        canonical_json_bytes(refusal["exception_reasons"])
    )
    assert module._address_is_current(
        refusal,
        identifier_field="refusal_id",
        digest_field="refusal_sha256",
        prefix="arv2-firm-named-refusal-",
    )
    assert module._address_is_current(
        context.ledger,
        identifier_field="ledger_id",
        digest_field="ledger_sha256",
        prefix="arv2-firm-refusal-ledger-",
    )
    assert module._address_is_current(
        context.decision,
        identifier_field="decision_id",
        digest_field="decision_sha256",
        prefix="arv2-firm-owner-decision-",
    )


def test_exact_74_rows_have_one_and_only_one_exact_status(context):
    rows = context.decision["firms"]
    accepted = {
        row["provider_firm_id"]
        for row in rows
        if row["decision_status"]
        == FirmOntologyOwnerDecisionStatus.ACCEPTED_DETERMINISTIC_DEFAULT.value
    }
    refused = {
        row["provider_firm_id"]
        for row in rows
        if row["decision_status"]
        == FirmOntologyOwnerDecisionStatus.NAMED_REFUSAL.value
    }
    assert len(rows) == len({row["provider_firm_id"] for row in rows}) == 74
    assert accepted.isdisjoint(refused)
    assert accepted | refused == {row["provider_firm_id"] for row in rows}
    assert {row["decision_status"] for row in rows} == {
        item.value for item in FirmOntologyOwnerDecisionStatus
    }
    assert context.decision["census"] == {
        "expected_firm_count": 74,
        "decision_firm_count": 74,
        "accepted_firm_count": 73,
        "refused_firm_count": 1,
        "availability_proxy_count": 146,
        "refusal_ledger_entry_count": 1,
    }


def test_equal_copy_is_not_builder_authority(context):
    clone = dataclasses.replace(context.artifact)
    with pytest.raises(
        FirmOntologyOwnerDecisionError,
        match="firm owner-decision is not current builder authority",
    ):
        require_firm_ontology_owner_decision(clone)


def test_parent_proposal_is_reauthenticated(tmp_path):
    context = _build_context(tmp_path)
    with context.proposal.path.open("ab") as handle:
        handle.write(b"\n")
    with pytest.raises(
        FirmOntologyOwnerDecisionError,
        match="firm owner-decision parent did not reauthenticate",
    ):
        require_firm_ontology_owner_decision(context.artifact)


def test_parent_packet_is_reauthenticated(tmp_path):
    context = _build_context(tmp_path)
    source = context.packet.archive_path / context.packet.files[0].relative_path
    with source.open("ab") as handle:
        handle.write(b"\n")
    with pytest.raises(
        FirmOntologyOwnerDecisionError,
        match="firm owner-decision parent did not reauthenticate",
    ):
        require_firm_ontology_owner_decision(context.artifact)


def test_parent_types_are_exact_before_any_parent_access():
    with pytest.raises(
        FirmOntologyOwnerDecisionError,
        match="firm owner-decision requires exact parent authority types",
    ):
        build_firm_ontology_owner_decision(
            review_packet=object(),
            proposal=object(),
        )


def test_proposal_must_bind_the_exact_packet(context, tmp_path):
    _c1_value, different_packet = _packet(tmp_path / "different")
    with pytest.raises(
        FirmOntologyOwnerDecisionError,
        match="firm owner-decision proposal and packet parents do not bind",
    ):
        build_firm_ontology_owner_decision(
            review_packet=different_packet,
            proposal=context.proposal,
        )


def test_process_authority_cannot_cross_pid(context, monkeypatch):
    owner_pid = os.getpid()
    monkeypatch.setattr(module.os, "getpid", lambda: owner_pid + 1)
    with pytest.raises(
        FirmOntologyOwnerDecisionError,
        match="firm owner-decision is not current process authority",
    ):
        require_firm_ontology_owner_decision(context.artifact)


def test_dependency_rebinding_is_refused_before_parent_access(context, monkeypatch):
    monkeypatch.setattr(
        module._availability,
        "resolve_delayed_date_only_session_open",
        lambda **_kwargs: None,
    )
    with pytest.raises(
        FirmOntologyOwnerDecisionError,
        match="firm owner-decision dependency binding changed",
    ):
        require_firm_ontology_owner_decision(context.artifact)


@pytest.mark.parametrize(
    ("target", "name"),
    (
        (module._proposal, "FirmOntologyProposalArtifact"),
        (module._proposal, "require_firm_ontology_proposal"),
        (module._proposal, "iter_firm_ontology_proposal_firms"),
        (module._packet, "PhysicalFirmOntologyReviewPacket"),
        (module._packet, "require_physical_firm_ontology_review_packet"),
        (module._canonical, "canonical_json_bytes"),
        (module._canonical, "sha256_bytes"),
        (module._canonical, "decode_utf8"),
        (module._canonical, "strict_json_loads"),
        (module._canonical, "require_identifier"),
        (module._canonical, "require_sha256"),
        (module, "canonical_json_bytes"),
        (module, "sha256_bytes"),
        (module, "decode_utf8"),
        (module, "strict_json_loads"),
        (module, "require_identifier"),
        (module, "require_sha256"),
        (module, "FirmOntologyOwnerDecisionStatus"),
        *((module, name) for name in module._BUILD_HELPER_NAMES),
    ),
)
def test_each_dependency_binding_is_isolated(
    context, monkeypatch, target, name
):
    monkeypatch.setattr(target, name, object())
    with pytest.raises(
        FirmOntologyOwnerDecisionError,
        match="firm owner-decision dependency binding changed",
    ):
        require_firm_ontology_owner_decision(context.artifact)


@pytest.mark.parametrize("operation", ("build", "require"))
def test_proposal_row_reauthentication_failure_is_normalized(
    context, monkeypatch, operation
):
    def refuse_rows(_proposal):
        raise module._proposal.FirmOntologyProposalError(
            "injected row authentication failure"
        )

    monkeypatch.setattr(
        module._proposal,
        "iter_firm_ontology_proposal_firms",
        refuse_rows,
    )
    monkeypatch.setattr(module, "_PINNED_PROPOSAL_ITERATOR", refuse_rows)
    with pytest.raises(
        FirmOntologyOwnerDecisionError,
        match="firm owner-decision proposal rows did not reauthenticate",
    ):
        if operation == "build":
            build_firm_ontology_owner_decision(
                review_packet=context.packet,
                proposal=context.proposal,
            )
        else:
            require_firm_ontology_owner_decision(context.artifact)


@pytest.mark.parametrize(
    ("bound", "message"),
    (
        (
            "decision",
            "mixed owner-decision document exceeds its fixed byte bound",
        ),
        (
            "ledger",
            "named-refusal ledger exceeds its fixed byte bound",
        ),
    ),
)
def test_each_output_byte_bound_is_isolated(context, monkeypatch, bound, message):
    if bound == "decision":
        monkeypatch.setattr(module, "MAX_DECISION_BYTES", 1)
    else:
        monkeypatch.setattr(module, "MAX_REFUSAL_LEDGER_BYTES", 1)
    with pytest.raises(FirmOntologyOwnerDecisionError, match=message):
        build_firm_ontology_owner_decision(
            review_packet=context.packet,
            proposal=context.proposal,
        )


def test_noncanonical_proposal_copy_is_refused():
    with pytest.raises(
        FirmOntologyOwnerDecisionError,
        match="test proposal value is not bounded canonical JSON",
    ):
        module._canonical_copy({object()}, "test proposal value")


@pytest.mark.parametrize(
    ("payload", "message"),
    (
        (b"not-json", "mixed owner decision is not strict JSON"),
        (b'{ "schema":"changed"}\n', "mixed owner decision is not one canonical object"),
    ),
)
def test_decision_decoder_refusals_are_distinctive(context, payload, message):
    clone = _authorize_test_clone(
        context,
        decision_bytes=payload,
        decision_payload_sha256=sha256_bytes(payload),
    )
    try:
        with pytest.raises(FirmOntologyOwnerDecisionError, match=message):
            require_firm_ontology_owner_decision(clone)
    finally:
        _forget_test_clone(clone)


def test_parent_authority_unavailable_is_distinctive(context):
    clone = _authorize_test_clone(context)
    authority = module._AUTHORITIES[id(clone)]
    module._AUTHORITIES[id(clone)] = (
        authority[0],
        authority[1],
        lambda: None,
        authority[3],
        authority[4],
    )
    try:
        with pytest.raises(
            FirmOntologyOwnerDecisionError,
            match="firm owner-decision parent authority is unavailable",
        ):
            require_firm_ontology_owner_decision(clone)
    finally:
        _forget_test_clone(clone)


def test_artifact_content_binding_is_distinctive(context):
    clone = _authorize_test_clone(
        context,
        decision_payload_sha256="0" * 64,
    )
    try:
        with pytest.raises(
            FirmOntologyOwnerDecisionError,
            match="firm owner-decision artifact or parent binding changed",
        ):
            require_firm_ontology_owner_decision(clone)
    finally:
        _forget_test_clone(clone)


def test_artifact_projection_is_distinctive(context):
    clone = _authorize_test_clone(
        context,
        accepted_firm_count=context.artifact.accepted_firm_count + 1,
    )
    try:
        with pytest.raises(
            FirmOntologyOwnerDecisionError,
            match="firm owner-decision artifact projection changed",
        ):
            require_firm_ontology_owner_decision(clone)
    finally:
        _forget_test_clone(clone)


def _refresh_evidence(evidence: dict[str, object]) -> None:
    evidence["evidence_id"] = None
    evidence["evidence_sha256"] = None
    digest = sha256_bytes(canonical_json_bytes(evidence))
    evidence["evidence_id"] = f"arv2-firm-proposal-evidence-{digest[:24]}"
    evidence["evidence_sha256"] = digest


def _compose(context, firms):
    return module._compose_documents(
        proposal_firms=tuple(firms),
        packet_id=context.packet.packet_id,
        packet_sha256=context.packet.packet_sha256,
        proposal_id=context.proposal.proposal_id,
        proposal_sha256=context.proposal.proposal_sha256,
        proposal_payload_sha256=context.proposal.payload_sha256,
    )


@pytest.mark.parametrize(
    ("case", "message"),
    (
        (
            "census",
            "mixed owner decision requires the exact 74-firm proposal census",
        ),
        ("row-type", "mixed owner decision proposal firm row changed type"),
        (
            "identity",
            "mixed owner decision firm identity is duplicated or out of order",
        ),
        (
            "policy-type",
            "mixed owner decision proposal policy fields changed type",
        ),
        (
            "partition",
            "mixed owner decision proposal policy partition is inconsistent",
        ),
        ("defaults-type", "accepted proposal defaults changed type"),
        (
            "scale",
            "accepted proposal defaults lack an explicit scale",
        ),
        ("mapping-type", "accepted proposal mapping row changed type"),
        ("missing-evidence", "accepted proposal mapping lacks exact evidence"),
        (
            "evidence-identity",
            "accepted proposal mapping evidence identity is invalid",
        ),
        (
            "evidence-binding",
            "accepted proposal mapping evidence lost its exact binding",
        ),
        (
            "availability-date",
            "conservative availability proxy cannot resolve its evidence date",
        ),
        (
            "refusal-reasons",
            "named refusal lacks exact unresolved labels or reasons",
        ),
    ),
)
def test_composition_load_bearing_refusals_are_isolated(context, case, message):
    firms = copy.deepcopy(list(context.proposal_firms))
    accepted = firms[1]
    mapping = accepted["proposed_defaults"]["ordered_scale"][0]
    if case == "census":
        firms.pop()
    elif case == "row-type":
        firms[0] = None
    elif case == "identity":
        firms[1]["provider_firm_id"] = firms[0]["provider_firm_id"]
    elif case == "policy-type":
        firms[0]["bulk_ratification_eligible"] = "no"
    elif case == "partition":
        accepted["exception_reasons"] = ["injected"]
    elif case == "defaults-type":
        accepted["proposed_defaults"] = None
    elif case == "scale":
        accepted["proposed_defaults"]["ordered_scale"] = []
    elif case == "mapping-type":
        accepted["proposed_defaults"]["ordered_scale"][0] = None
    elif case == "missing-evidence":
        mapping["mapping_evidence"] = None
    elif case == "evidence-identity":
        mapping["mapping_evidence"]["evidence_id"] = ""
    elif case == "evidence-binding":
        evidence = mapping["mapping_evidence"]
        evidence["raw_label"] = "injected"
        _refresh_evidence(evidence)
    elif case == "availability-date":
        evidence = mapping["mapping_evidence"]
        evidence["first_event_date"] = "1989-12-31"
        _refresh_evidence(evidence)
    else:
        firms[0]["exception_reasons"] = [1]

    with pytest.raises(FirmOntologyOwnerDecisionError, match=message):
        _compose(context, firms)


@pytest.mark.parametrize(
    ("case", "message"),
    (
        ("decision-fields", "mixed owner-decision document fields changed"),
        ("ledger-fields", "named-refusal ledger fields changed"),
        ("parent", "mixed owner-decision parent bindings changed"),
        ("schema", "mixed owner-decision schema changed"),
        ("ledger-address", "named-refusal ledger content address changed"),
        ("decision-address", "mixed owner-decision content address changed"),
        (
            "capabilities",
            "mixed owner-decision non-authority capabilities changed",
        ),
        ("policy", "mixed owner-decision frozen policy changed"),
        ("coverage", "mixed owner-decision firm coverage is not exactly 74"),
        ("entries-type", "named-refusal ledger entries changed type"),
        ("entry-fields", "named-refusal ledger entry fields changed"),
        ("entry-repeat", "named-refusal ledger repeats an entry identity"),
        (
            "entry-status",
            "named-refusal ledger entry status or content address changed",
        ),
        ("firm-fields", "mixed owner-decision firm row fields changed"),
        (
            "firm-order",
            "mixed owner-decision firm coverage overlaps or is out of order",
        ),
        ("firm-source", "mixed owner-decision firm source binding changed"),
        ("status-enum", "mixed owner-decision status is outside the exact enum"),
        (
            "status-policy",
            "mixed owner-decision status contradicts authenticated proposal policy",
        ),
        (
            "accepted-default",
            "accepted firm defaults are not the exact authenticated proposal copy",
        ),
        ("accepted-proxy", "accepted firm proxy or refusal binding changed"),
        (
            "refused-mapping",
            "named-refusal firm carries mappings or accepted defaults",
        ),
        (
            "refusal-binding",
            "named refusal does not bind exact proposal labels and reasons",
        ),
        (
            "ledger-coverage",
            "named-refusal ledger order, coverage, or decision binding changed",
        ),
        ("census", "mixed owner-decision census changed"),
        (
            "ledger-binding",
            "mixed owner-decision refusal-ledger binding changed",
        ),
    ),
)
def test_document_load_bearing_refusals_are_isolated(context, case, message):
    decision = copy.deepcopy(context.decision)
    ledger = copy.deepcopy(context.ledger)
    accepted = decision["firms"][1]
    refused = decision["firms"][0]
    entry = ledger["entries"][0]
    refreshed = False
    if case == "decision-fields":
        decision.pop("policy")
    elif case == "ledger-fields":
        ledger.pop("expected_firm_count")
    elif case == "parent":
        decision["source"]["proposal_id"] = "changed-proposal"
    elif case == "schema":
        decision["schema"] = "changed-schema"
    elif case == "ledger-address":
        ledger["ledger_sha256"] = "0" * 64
    elif case == "decision-address":
        decision["decision_sha256"] = "0" * 64
    elif case == "capabilities":
        decision["capabilities"]["production_authority"] = True
        refreshed = True
    elif case == "policy":
        decision["policy"]["accepted_mapping_source"] = "changed"
        refreshed = True
    elif case == "coverage":
        decision["firms"].pop()
        refreshed = True
    elif case == "entries-type":
        ledger["entries"] = {}
        refreshed = True
    elif case == "entry-fields":
        entry.pop("exception_reasons_sha256")
        refreshed = True
    elif case == "entry-repeat":
        ledger["entries"].append(copy.deepcopy(entry))
        refreshed = True
    elif case == "entry-status":
        entry["decision_status"] = "accepted_deterministic_default"
        _refresh_entry(entry)
        refreshed = True
    elif case == "firm-fields":
        accepted.pop("refusal_sha256")
        refreshed = True
    elif case == "firm-order":
        decision["firms"][1], decision["firms"][2] = (
            decision["firms"][2],
            decision["firms"][1],
        )
        refreshed = True
    elif case == "firm-source":
        accepted["firm_evidence_row_sha256"] = "0" * 64
        refreshed = True
    elif case == "status-enum":
        accepted["decision_status"] = "accepted"
        refreshed = True
    elif case == "status-policy":
        accepted["decision_status"] = "named_refusal"
        refreshed = True
    elif case == "accepted-default":
        accepted["accepted_proposal_defaults"]["canonical_firm_name"] = "Changed"
        accepted["accepted_proposal_defaults_sha256"] = sha256_bytes(
            canonical_json_bytes(accepted["accepted_proposal_defaults"])
        )
        refreshed = True
    elif case == "accepted-proxy":
        accepted["availability_proxies"][0]["proxy_session"] = "2021-01-06"
        refreshed = True
    elif case == "refused-mapping":
        refused["accepted_proposal_defaults"] = {}
        refused["accepted_proposal_defaults_sha256"] = sha256_bytes(b"{}")
        refreshed = True
    elif case == "refusal-binding":
        entry["exception_reasons"].append("injected")
        entry["exception_reasons_sha256"] = sha256_bytes(
            canonical_json_bytes(entry["exception_reasons"])
        )
        _refresh_entry(entry)
        refused["refusal_sha256"] = entry["refusal_sha256"]
        refreshed = True
    elif case == "ledger-coverage":
        extra = copy.deepcopy(entry)
        extra["provider_firm_id"] = "unbound-firm"
        _refresh_entry(extra)
        ledger["entries"].append(extra)
        refreshed = True
    elif case == "census":
        decision["census"]["accepted_firm_count"] += 1
        refreshed = True
    else:
        decision["refusal_ledger"]["ledger_id"] = "changed-ledger"
        module._address_record(
            decision,
            identifier_field="decision_id",
            digest_field="decision_sha256",
            prefix="arv2-firm-owner-decision-",
        )

    if refreshed:
        _refresh_documents(decision, ledger)
    with pytest.raises(FirmOntologyOwnerDecisionError, match=message):
        _validate(context, decision, ledger)
