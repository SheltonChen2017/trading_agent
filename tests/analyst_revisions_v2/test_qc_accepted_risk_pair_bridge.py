"""Focused tests for the physical Massive-to-formal accepted-risk bridge."""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re

import pytest

from research.analyst_revisions_v2.canonical import CanonicalEvidenceError
from research.analyst_revisions_v2.production_input_pipeline import (
    SignalArm,
    build_production_evidence_authority,
    build_production_input_batch,
)
from research.analyst_revisions_v2_qc import accepted_risk_pair_bridge as bridge_module
from research.analyst_revisions_v2_qc.accepted_risk_pair_bridge import (
    PAIR_ARTIFACT_DOMAIN,
    AcceptedRiskPairBridgeError,
    build_formal_accepted_risk_pair_binding,
    render_formal_accepted_risk_pair_artifact_bytes,
)
from research.analyst_revisions_v2_qc.formal_run_protocol import (
    FormalRunProtocolError,
    require_accepted_risk_pair_binding,
)
from scripts.build_arv2_massive_input_pair import (
    _build_massive_accepted_risk_input_pair_for_test,
)
from tests.analyst_revisions_v2.test_massive_capture_adapter import (
    FakeResponse,
    ROLE_ORDER,
    _capture,
    _endpoint,
    _payload,
    _row,
)
from tests.analyst_revisions_v2.test_production_input_pipeline import (
    _rating_row,
    _row_evidence,
    _sources,
)


def _parents(tmp_path, monkeypatch):
    loaded, _ = _capture(tmp_path, monkeypatch)
    massive = _build_massive_accepted_risk_input_pair_for_test(
        loaded.artifact_path
    )
    authority = build_production_evidence_authority(
        massive.pair,
        source_bindings=_sources(),
        row_evidence=(),
    )
    current = build_production_input_batch(
        authority, signal_arm=SignalArm.CURRENT_VINTAGE
    )
    censored = build_production_input_batch(
        authority, signal_arm=SignalArm.CONSERVATIVE_CENSORED
    )
    return massive, current, censored


def _parents_with_one_admitted_revision(tmp_path, monkeypatch):
    rating = _rating_row(
        "rating-up",
        event_date="2021-01-04",
        last_updated="2021-01-04T13:30:00Z",
    )
    responses = [
        FakeResponse(_payload([rating]), _endpoint(ROLE_ORDER[0])),
        FakeResponse(
            _payload([_row("earnings-1", role=ROLE_ORDER[1])]),
            _endpoint(ROLE_ORDER[1]),
        ),
        FakeResponse(
            _payload([_row("guidance-1", role=ROLE_ORDER[2])]),
            _endpoint(ROLE_ORDER[2]),
        ),
    ]
    loaded, _ = _capture(tmp_path, monkeypatch, responses=responses)
    massive = _build_massive_accepted_risk_input_pair_for_test(
        loaded.artifact_path
    )
    source = next(
        row for row in massive.pair.rows if row.provider_event_id == "rating-up"
    )
    assert source.current_view.eligible_session is not None
    evidence = _row_evidence(
        source,
        security_id="security-meta",
        historical_ticker="FB",
    )
    evidence = dataclasses.replace(
        evidence,
        control=dataclasses.replace(
            evidence.control,
            decision_session=source.current_view.eligible_session,
        ),
        q_data=dataclasses.replace(
            evidence.q_data,
            measured_session=source.current_view.eligible_session,
        ),
    )
    authority = build_production_evidence_authority(
        massive.pair,
        source_bindings=_sources(),
        row_evidence=(evidence,),
    )
    current = build_production_input_batch(
        authority, signal_arm=SignalArm.CURRENT_VINTAGE
    )
    censored = build_production_input_batch(
        authority, signal_arm=SignalArm.CONSERVATIVE_CENSORED
    )
    return massive, current, censored


def test_physical_pair_renders_exact_canonical_artifact_and_formal_binding(
    tmp_path, monkeypatch
):
    massive, current, censored = _parents(tmp_path, monkeypatch)

    payload = render_formal_accepted_risk_pair_artifact_bytes(massive)
    binding = build_formal_accepted_risk_pair_binding(
        bridge=massive,
        current_batch=current,
        censored_batch=censored,
    )

    assert payload.endswith(b"\n")
    assert hashlib.sha256(payload).hexdigest() == massive.pair.pair_sha256
    document = json.loads(payload)
    assert document["capture_id"] == massive.pair.capture.capture_id
    assert document["capture_sha256"] == massive.pair.capture.capture_sha256
    assert len(document["rows"]) == len(massive.pair.rows)
    assert document["pristine_point_in_time"] is False
    assert document["earlier_version_imputation_performed"] is False
    assert document["views_share_one_capture"] is True
    assert document["production_input_authority"] is False
    assert document["outcome_gate_open"] is False
    assert document["provider_binding"] is None
    assert document["security_master_binding"] is None
    assert document["outcome_binding"] is None
    assert require_accepted_risk_pair_binding(binding) is binding
    assert binding.pair.artifact_id == massive.pair.pair_id
    assert binding.pair.content_sha256 == massive.pair.pair_sha256
    assert binding.pair.artifact_sha256 == hashlib.sha256(
        PAIR_ARTIFACT_DOMAIN + payload
    ).hexdigest()
    assert binding.pair.byte_count == len(payload)
    assert binding.capture_id == massive.pair.capture.capture_id
    assert binding.capture_sha256 == massive.pair.capture.capture_sha256
    assert binding.current_source_included_count == current.source_view_included_count
    assert binding.censored_source_included_count == censored.source_view_included_count
    assert binding.current_admitted_decision_count == current.normalized_row_count
    assert binding.censored_admitted_decision_count == censored.normalized_row_count
    assert binding.current_named_preoutcome_refusal_count == (
        current.source_view_included_count - current.normalized_row_count
    )
    assert binding.censored_named_preoutcome_refusal_count == (
        censored.source_view_included_count - censored.normalized_row_count
    )
    assert binding.guidance_admitted_count == 0
    assert binding.pre_2013_admitted_count == 0
    assert binding.pristine_point_in_time is False
    assert binding.views_share_one_capture is True


def test_formal_binding_refuses_swapped_source_view_batches(tmp_path, monkeypatch):
    massive, current, censored = _parents(tmp_path, monkeypatch)

    with pytest.raises(
        AcceptedRiskPairBridgeError,
        match=re.escape(
            "current and censored batches do not share the exact Massive pair"
        ),
    ):
        build_formal_accepted_risk_pair_binding(
            bridge=massive,
            current_batch=censored,
            censored_batch=current,
        )


def test_formal_binding_derives_nonzero_admission_and_refusal_counts(
    tmp_path, monkeypatch
):
    massive, current, censored = _parents_with_one_admitted_revision(
        tmp_path, monkeypatch
    )
    assert current.normalized_row_count == censored.normalized_row_count == 1

    binding = build_formal_accepted_risk_pair_binding(
        bridge=massive,
        current_batch=current,
        censored_batch=censored,
    )

    assert binding.current_admitted_decision_count == 1
    assert binding.censored_admitted_decision_count == 1
    assert binding.current_named_preoutcome_refusal_count == (
        binding.current_source_included_count - 1
    )
    assert binding.censored_named_preoutcome_refusal_count == (
        binding.censored_source_included_count - 1
    )


def test_formal_binding_refuses_batches_from_an_equal_but_distinct_pair(
    tmp_path, monkeypatch
):
    massive, _, _ = _parents(tmp_path / "first", monkeypatch)
    other, current, censored = _parents(tmp_path / "second", monkeypatch)
    assert other.pair.pair_sha256 == massive.pair.pair_sha256
    assert other.pair is not massive.pair

    with pytest.raises(
        AcceptedRiskPairBridgeError,
        match=re.escape(
            "current and censored batches do not share the exact Massive pair"
        ),
    ):
        build_formal_accepted_risk_pair_binding(
            bridge=massive,
            current_batch=current,
            censored_batch=censored,
        )


def test_formal_binding_refuses_a_changed_authenticated_batch(tmp_path, monkeypatch):
    massive, current, censored = _parents(tmp_path, monkeypatch)
    object.__setattr__(current, "normalized_row_count", 1)

    with pytest.raises(
        AcceptedRiskPairBridgeError,
        match=re.escape("accepted-risk production batches did not authenticate"),
    ):
        build_formal_accepted_risk_pair_binding(
            bridge=massive,
            current_batch=current,
            censored_batch=censored,
        )


def test_renderer_uses_pinned_canonicalizer_and_semantic_projection(
    tmp_path, monkeypatch
):
    massive, _, _ = _parents(tmp_path, monkeypatch)
    expected = render_formal_accepted_risk_pair_artifact_bytes(massive)

    monkeypatch.setattr(
        bridge_module,
        "canonical_json_bytes",
        lambda _value: b"attacker-controlled\n",
    )
    monkeypatch.setattr(
        bridge_module,
        "_pair_semantic_record",
        lambda _pair: {"attacker": True},
    )

    assert render_formal_accepted_risk_pair_artifact_bytes(massive) == expected


def test_renderer_refuses_a_projection_that_does_not_reproduce_pair_hash(
    tmp_path, monkeypatch
):
    massive, _, _ = _parents(tmp_path, monkeypatch)
    monkeypatch.setattr(
        bridge_module,
        "_PINNED_PAIR_SEMANTIC_RECORD",
        lambda _pair: {"schema": "wrong-semantic-projection"},
    )

    with pytest.raises(
        AcceptedRiskPairBridgeError,
        match=re.escape(
            "accepted-risk pair artifact does not reproduce its content hash"
        ),
    ):
        render_formal_accepted_risk_pair_artifact_bytes(massive)


def test_renderer_normalizes_a_canonical_render_failure(tmp_path, monkeypatch):
    massive, _, _ = _parents(tmp_path, monkeypatch)

    def refuse_render(_value):
        raise CanonicalEvidenceError("synthetic canonical-render failure")

    monkeypatch.setattr(
        bridge_module,
        "_PINNED_CANONICAL_JSON_BYTES",
        refuse_render,
    )
    with pytest.raises(
        AcceptedRiskPairBridgeError,
        match=re.escape("accepted-risk pair artifact could not be rendered"),
    ):
        render_formal_accepted_risk_pair_artifact_bytes(massive)


def test_formal_binding_normalizes_artifact_binding_failure(tmp_path, monkeypatch):
    massive, current, censored = _parents(tmp_path, monkeypatch)

    def refuse_artifact(**_values):
        raise FormalRunProtocolError("synthetic artifact-binding failure")

    monkeypatch.setattr(
        bridge_module,
        "_PINNED_ARTIFACT_BINDING_TYPE",
        refuse_artifact,
    )
    with pytest.raises(
        AcceptedRiskPairBridgeError,
        match=re.escape("accepted-risk pair artifact binding could not be built"),
    ):
        build_formal_accepted_risk_pair_binding(
            bridge=massive,
            current_batch=current,
            censored_batch=censored,
        )


def test_formal_binding_normalizes_final_protocol_refusal(tmp_path, monkeypatch):
    massive, current, censored = _parents(tmp_path, monkeypatch)

    def refuse_binding(**_values):
        raise FormalRunProtocolError("synthetic formal-binding failure")

    monkeypatch.setattr(
        bridge_module,
        "_PINNED_ACCEPTED_BINDING_TYPE",
        refuse_binding,
    )
    with pytest.raises(
        AcceptedRiskPairBridgeError,
        match=re.escape(
            "formal accepted-risk pair binding refused derived state"
        ),
    ):
        build_formal_accepted_risk_pair_binding(
            bridge=massive,
            current_batch=current,
            censored_batch=censored,
        )


def test_renderer_refuses_a_changed_physical_bridge(tmp_path, monkeypatch):
    massive, _, _ = _parents(tmp_path, monkeypatch)
    object.__setattr__(massive, "pristine_point_in_time", True)

    with pytest.raises(
        AcceptedRiskPairBridgeError,
        match=re.escape("Massive accepted-risk bridge did not authenticate"),
    ):
        render_formal_accepted_risk_pair_artifact_bytes(massive)
