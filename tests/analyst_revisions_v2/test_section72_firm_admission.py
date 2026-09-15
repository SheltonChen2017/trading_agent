from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from research.analyst_revisions_v2_qc import production_evidence_composer as module
from tests.analyst_revisions_v2.test_firm_ontology_owner_decision import (
    _build_context,
)


def _exact(message: str) -> str:
    return f"^{re.escape(message)}$"


@pytest.fixture(scope="module")
def context(tmp_path_factory):
    return _build_context(tmp_path_factory.mktemp("section72-firm-admission"))


@pytest.fixture(scope="module")
def admission(context):
    return module.build_section72_owner_waived_firm_admission(
        decision=context.artifact, review_packet=context.packet
    )


def test_admission_copies_clean_defaults_and_excludes_every_named_refusal(
    context, admission
):
    assert module.require_section72_owner_waived_firm_admission(admission) is admission
    assert admission.owner_decision is context.artifact
    assert admission.accepted_firm_count == context.artifact.accepted_firm_count
    assert admission.refused_firm_count == context.artifact.refused_firm_count
    assert admission.mapping_count == context.artifact.availability_proxy_count
    assert len(admission.mappings) == admission.mapping_count
    assert len(admission.refused_provider_firm_ids) == admission.refused_firm_count
    assert all(
        item.provider_firm_id not in admission.refused_provider_firm_ids
        for item in admission.mappings
    )
    assert all(
        item.proxy_kind == module._firm_decision.AVAILABILITY_PROXY_KIND
        for item in admission.mappings
    )
    assert admission.deterministic_defaults_only is True
    assert admission.named_refusals_excluded is True
    assert admission.conservative_availability_proxy_only is True
    assert admission.owner_signature_required_downstream is True
    assert admission.independently_reviewed is False
    assert admission.historical_availability_claimed is False
    assert admission.normal_registry_populated is False
    assert admission.production_authority is False


def test_admission_is_deterministic_and_iterable(context, admission):
    second = module.build_section72_owner_waived_firm_admission(
        decision=context.artifact, review_packet=context.packet
    )
    assert second.admission_id == admission.admission_id
    assert second.admission_sha256 == admission.admission_sha256
    assert [item.to_record() for item in second.mappings] == [
        item.to_record()
        for item in module.iter_section72_owner_waived_firm_mappings(admission)
    ]


def test_admission_requires_exact_decision_type():
    with pytest.raises(
        module.ProductionEvidenceComposerError,
        match=_exact(
            "owner-waived firm admission requires exact owner-decision type"
        ),
    ):
        module.build_section72_owner_waived_firm_admission(
            decision=object(), review_packet=object()
        )


def test_admission_requires_exact_review_packet_type(context):
    with pytest.raises(
        module.ProductionEvidenceComposerError,
        match=_exact(
            "owner-waived firm admission requires exact review-packet type"
        ),
    ):
        module.build_section72_owner_waived_firm_admission(
            decision=context.artifact, review_packet=object()
        )


def test_admission_rejects_forged_unregistered_instance(admission):
    forged = object.__new__(module.OwnerWaivedAcceptedRiskFirmAdmission)
    for field in module.dataclasses.fields(admission):
        object.__setattr__(forged, field.name, getattr(admission, field.name))
    with pytest.raises(
        module.ProductionEvidenceComposerError,
        match=_exact("owner-waived firm admission lost builder authority"),
    ):
        module.require_section72_owner_waived_firm_admission(forged)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("deterministic_defaults_only", False),
        ("named_refusals_excluded", False),
        ("conservative_availability_proxy_only", False),
        ("owner_signature_required_downstream", False),
        ("independently_reviewed", True),
        ("historical_availability_claimed", True),
        ("normal_registry_populated", True),
        ("production_authority", True),
    ),
)
def test_each_admission_policy_flag_is_load_bearing(admission, field, value):
    original = getattr(admission, field)
    object.__setattr__(admission, field, value)
    try:
        with pytest.raises(
            module.ProductionEvidenceComposerError,
            match=_exact("owner-waived firm admission lost builder authority"),
        ):
            module.require_section72_owner_waived_firm_admission(admission)
    finally:
        object.__setattr__(admission, field, original)


def test_admission_parent_reauthentication_is_load_bearing(
    monkeypatch, context, admission
):
    def reject(_value):
        raise module._firm_decision.FirmOntologyOwnerDecisionError("test")

    monkeypatch.setattr(
        module._firm_decision, "require_firm_ontology_owner_decision", reject
    )
    with pytest.raises(
        module.ProductionEvidenceComposerError,
        match=_exact("owner-waived firm admission parent did not reauthenticate"),
    ):
        module.require_section72_owner_waived_firm_admission(admission)


def test_owner_waived_component_accepts_only_admitted_mapping(admission):
    by_firm: dict[str, list[module.OwnerWaivedFirmMapping]] = {}
    for mapping in admission.mappings:
        by_firm.setdefault(mapping.provider_firm_id, []).append(mapping)
    current = previous = None
    for values in by_firm.values():
        ranks = {item.ordered_rank for item in values}
        if len(ranks) >= 2:
            previous = min(values, key=lambda item: item.ordered_rank)
            current = max(values, key=lambda item: item.ordered_rank)
            break
    assert current is not None and previous is not None
    source = SimpleNamespace(
        event_date=current.valid_from,
        provider_event_id="event-section72-test",
        firm_label=current.provider_firm_id,
    )
    raw = {
        "benzinga_firm_id": current.provider_firm_id,
        "firm": current.firm_name,
        "rating": current.raw_label,
        "previous_rating": previous.raw_label,
    }

    evidence, status = module._owner_waived_firm_component(
        source=source, raw=raw, admission=admission
    )

    assert status == "accepted"
    assert type(evidence) is module.Section72OwnerWaivedFirmOntologyEvidence
    assert evidence.ontology_id == admission.admission_id
    assert evidence.ontology_reviewed is False
    assert evidence.labels_reviewed is False
    assert evidence.independently_reviewed is False
    assert evidence.historical_availability_claimed is False
    assert evidence.deterministic_default is True
    assert evidence.named_refusal is False
    assert evidence.current_score == current.normalized_score
    assert evidence.previous_score == previous.normalized_score
    assert evidence.available_at == max(
        datetime.fromisoformat(value).astimezone(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S.%fZ"
        )
        for value in (current.proxy_open_at, previous.proxy_open_at)
    )


def test_owner_waived_component_excludes_named_refusal(admission):
    refused = admission.refused_provider_firm_ids[0]
    source = SimpleNamespace(
        event_date="2021-01-04",
        provider_event_id="event-section72-refused",
        firm_label=refused,
    )
    evidence, status = module._owner_waived_firm_component(
        source=source,
        raw={
            "benzinga_firm_id": refused,
            "firm": "Refused Firm",
            "rating": "Buy",
            "previous_rating": "Hold",
        },
        admission=admission,
    )
    assert evidence is None
    assert status == "upstream_named_refusal"


def test_owner_waived_component_never_guesses_unknown_label(admission):
    mapping = admission.mappings[0]
    source = SimpleNamespace(
        event_date=mapping.valid_from,
        provider_event_id="event-section72-unknown",
        firm_label=mapping.provider_firm_id,
    )
    evidence, status = module._owner_waived_firm_component(
        source=source,
        raw={
            "benzinga_firm_id": mapping.provider_firm_id,
            "firm": mapping.firm_name,
            "rating": "not-an-authenticated-label",
            "previous_rating": mapping.raw_label,
        },
        admission=admission,
    )
    assert evidence is None
    assert status == "unreviewed_or_unavailable"
