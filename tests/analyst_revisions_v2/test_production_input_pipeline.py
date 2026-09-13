from __future__ import annotations

import ast
import dataclasses
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest

from research.analyst_revisions_v2 import production_input_pipeline as pipeline_module
from research.analyst_revisions_v2.accepted_risk_input_pair import (
    AcceptedRiskInputError,
    AcceptedRiskInputPair,
    MassiveSourceRole,
    bind_capture_page,
    build_accepted_risk_input_pair,
    build_capture_binding,
    render_redacted_capture_query_bytes,
)
from research.analyst_revisions_v2.canonical import canonical_json_bytes, sha256_bytes
from research.analyst_revisions_v2.production_input_pipeline import (
    AdmissionDisposition,
    ComparisonDimension,
    CommonEventIdentityEvidence,
    DataQualityEvidence,
    EvidenceSourceBinding,
    EvidenceSourceKind,
    FirmOntologyEvidence,
    NormalizedPreOutcomeRow,
    PRODUCTION_INPUT_CONTRACT_ID,
    PRODUCTION_INPUT_CONTRACT_SHA256,
    PreopenControlEvidence,
    ProductionEvidenceAuthority,
    ProductionInputBatch,
    ProductionInputError,
    ProductionRowEvidence,
    SectorClassificationEvidence,
    SecurityIdentityEvidence,
    SignalArm,
    build_production_evidence_authority,
    build_production_input_batch,
    build_production_input_comparison_report,
    production_input_contract_record,
    render_production_input_contract_bytes,
    require_production_evidence_authority,
    require_production_input_batch,
)


STARTED = "2026-09-11T18:00:00.000000Z"
COMPLETED = "2026-09-11T18:04:00.000000Z"
FIRST = "2011-01-01"
LAST = "2025-12-31"
EARLY = "2020-01-06T14:29:00.000000Z"
CUTOFF = "2020-01-06T14:30:00.000000Z"
SOURCE_HASHES = {
    kind: f"{index:x}" * 64
    for index, kind in enumerate(EvidenceSourceKind, start=1)
}
SOURCE_IDS = {
    EvidenceSourceKind.SECURITY_MASTER: "pit-security-master-1",
    EvidenceSourceKind.FIRM_ONTOLOGY: "firm-ontology-1",
    EvidenceSourceKind.COMMON_EVENT: "common-event-catalog-1",
    EvidenceSourceKind.SECTOR_CLASSIFICATION: "pit-sector-catalog-1",
    EvidenceSourceKind.PREOPEN_CONTROL: "preopen-control-catalog-1",
    EvidenceSourceKind.DATA_QUALITY: "q-data-catalog-1",
}
ROLE_RECEIPTS = {
    MassiveSourceRole.ANALYST_RATINGS: "2026-09-11T18:01:00.000000Z",
    MassiveSourceRole.EARNINGS: "2026-09-11T18:02:00.000000Z",
    MassiveSourceRole.CORPORATE_GUIDANCE: "2026-09-11T18:03:00.000000Z",
}


def _rating_row(
    event_id: str,
    *,
    event_date: str = "2020-01-02",
    last_updated: object = "2020-01-03T12:00:00Z",
    ticker: str = "META",
    action: str = "upgrades",
    rating: str = "Buy",
    previous_rating: str = "Sell",
    firm_id: str = "firm-1",
    firm: str = "Reviewed Firm",
    **extra,
):
    row = {
        "benzinga_id": event_id,
        "date": event_date,
        "time": "09:31:00",
        "last_updated": last_updated,
        "ticker": ticker,
        "rating_action": action,
        "rating": rating,
        "previous_rating": previous_rating,
        "benzinga_firm_id": firm_id,
        "firm": firm,
    }
    row.update(extra)
    return row


def _rows_bytes(rows) -> bytes:
    return b"".join(canonical_json_bytes(row) for row in rows)


def _page(role: MassiveSourceRole, rows):
    return bind_capture_page(
        source_role=role,
        redacted_query_bytes=render_redacted_capture_query_bytes(
            source_role=role,
            requested_first_event_date=FIRST,
            requested_last_event_date=LAST,
        ),
        page_number=1,
        request_cursor_sha256=None,
        next_cursor_sha256=None,
        terminal_page=True,
        response_received_at=ROLE_RECEIPTS[role],
        raw_response_sha256=SOURCE_HASHES[
            {
                MassiveSourceRole.ANALYST_RATINGS: EvidenceSourceKind.SECURITY_MASTER,
                MassiveSourceRole.EARNINGS: EvidenceSourceKind.FIRM_ONTOLOGY,
                MassiveSourceRole.CORPORATE_GUIDANCE: EvidenceSourceKind.COMMON_EVENT,
            }[role]
        ],
        provider_rows_bytes=_rows_bytes(rows),
    )


def _pair(*, ratings=None) -> AcceptedRiskInputPair:
    rating_rows = ratings or [
        _rating_row("rating-up"),
        _rating_row(
            "rating-late",
            last_updated="2020-01-07T12:00:00Z",
            ticker="GOOG",
            action="downgrades",
            rating="Sell",
            previous_rating="Buy",
        ),
        _rating_row(
            "rating-maintain",
            ticker="MSFT",
            action="maintains",
            rating="Buy",
            previous_rating="Buy",
        ),
        _rating_row(
            "rating-old",
            event_date="2012-01-03",
            last_updated="2012-01-04T12:00:00Z",
            ticker="AAPL",
        ),
    ]
    capture = build_capture_binding(
        capture_started_at=STARTED,
        capture_completed_at=COMPLETED,
        pages=(
            _page(MassiveSourceRole.ANALYST_RATINGS, rating_rows),
            _page(
                MassiveSourceRole.EARNINGS,
                [
                    {
                        "benzinga_id": "earnings-1",
                        "date": "2020-01-02",
                        "time": "09:31:00",
                        "last_updated": "2020-01-03T12:00:00Z",
                        "ticker": "META",
                    }
                ],
            ),
            _page(
                MassiveSourceRole.CORPORATE_GUIDANCE,
                [
                    {
                        "benzinga_id": "guidance-1",
                        "date": "2020-01-02",
                        "time": "09:31:00",
                        "last_updated": "2020-01-03T12:00:00Z",
                        "ticker": "META",
                    }
                ],
            ),
        ),
    )
    return build_accepted_risk_input_pair(capture)


def _sources(
    *,
    changed_kind: EvidenceSourceKind | None = None,
    reviewed: bool = True,
    point_in_time: bool = True,
):
    return tuple(
        EvidenceSourceBinding(
            kind=kind,
            artifact_id=SOURCE_IDS[kind],
            artifact_sha256=SOURCE_HASHES[kind],
            reviewed=(reviewed if kind is changed_kind else True),
            point_in_time=(point_in_time if kind is changed_kind else True),
        )
        for kind in EvidenceSourceKind
    )


def _row_evidence(source, *, security_id: str, historical_ticker: str):
    raw = source.locator.raw_row_sha256
    action = "downgrades" if source.provider_event_id == "rating-late" else "upgrades"
    if action == "upgrades":
        current_label, previous_label = "Buy", "Sell"
        current_score, previous_score = Fraction(1), Fraction(-1)
    else:
        current_label, previous_label = "Sell", "Buy"
        current_score, previous_score = Fraction(-1), Fraction(1)
    return ProductionRowEvidence(
        locator=source.locator,
        security=SecurityIdentityEvidence(
            provider_event_id=source.provider_event_id,
            source_current_restated_ticker=source.current_restated_security_label,
            historical_ticker=historical_ticker,
            issuer_id=f"issuer-{security_id}",
            security_id=security_id,
            share_class_id=f"share-{security_id}",
            listing_id=f"listing-{security_id}",
            security_master_id=SOURCE_IDS[EvidenceSourceKind.SECURITY_MASTER],
            security_master_sha256=SOURCE_HASHES[EvidenceSourceKind.SECURITY_MASTER],
            mapping_version_id=f"map-{security_id}",
            mapping_evidence_sha256=raw,
            valid_from="2010-01-01",
            valid_to=None,
            valid_to_available_at=None,
            available_at=EARLY,
            candidate_count=1,
            point_in_time=True,
            current_ticker_only=False,
        ),
        firm=FirmOntologyEvidence(
            provider_event_id=source.provider_event_id,
            provider_firm_id="firm-1",
            raw_firm_name="Reviewed Firm",
            raw_current_label=current_label,
            raw_previous_label=previous_label,
            institution_id="institution-1",
            ontology_id=SOURCE_IDS[EvidenceSourceKind.FIRM_ONTOLOGY],
            ontology_sha256=SOURCE_HASHES[EvidenceSourceKind.FIRM_ONTOLOGY],
            ontology_entry_sha256=sha256_bytes(
                canonical_json_bytes(["firm-1", current_label, previous_label])
            ),
            valid_from="2010-01-01",
            valid_to=None,
            valid_to_available_at=None,
            available_at=EARLY,
            current_score=current_score,
            previous_score=previous_score,
            candidate_count=1,
            ontology_reviewed=True,
            labels_reviewed=True,
        ),
        common_event=CommonEventIdentityEvidence(
            provider_event_id=source.provider_event_id,
            common_event_id=f"common-{source.provider_event_id}",
            source_id=SOURCE_IDS[EvidenceSourceKind.COMMON_EVENT],
            source_sha256=SOURCE_HASHES[EvidenceSourceKind.COMMON_EVENT],
            evidence_sha256=sha256_bytes(canonical_json_bytes(["common", raw])),
            available_at=EARLY,
            candidate_count=1,
        ),
        sector=SectorClassificationEvidence(
            security_id=security_id,
            sector_id="sector-technology",
            source_id=SOURCE_IDS[EvidenceSourceKind.SECTOR_CLASSIFICATION],
            source_sha256=SOURCE_HASHES[EvidenceSourceKind.SECTOR_CLASSIFICATION],
            evidence_sha256=sha256_bytes(canonical_json_bytes(["sector", raw])),
            valid_from="2010-01-01",
            valid_to=None,
            valid_to_available_at=None,
            available_at=EARLY,
            candidate_count=1,
            point_in_time=True,
        ),
        control=PreopenControlEvidence(
            security_id=security_id,
            industry_id="industry-software",
            decision_session="2020-01-06",
            source_id=SOURCE_IDS[EvidenceSourceKind.PREOPEN_CONTROL],
            source_sha256=SOURCE_HASHES[EvidenceSourceKind.PREOPEN_CONTROL],
            evidence_sha256=sha256_bytes(canonical_json_bytes(["control", raw])),
            available_at=EARLY,
            control_vector_sha256=sha256_bytes(canonical_json_bytes(["vector", raw])),
            complete=True,
            point_in_time=True,
            contains_outcome_or_price=False,
        ),
        q_data=DataQualityEvidence(
            security_id=security_id,
            measured_session="2020-01-06",
            source_id=SOURCE_IDS[EvidenceSourceKind.DATA_QUALITY],
            source_sha256=SOURCE_HASHES[EvidenceSourceKind.DATA_QUALITY],
            evidence_sha256=sha256_bytes(canonical_json_bytes(["quality", raw])),
            available_at=EARLY,
            measurement_method_id="q-data-method-1",
            q_data=Decimal("0.875"),
            point_in_time=True,
        ),
    )


def _evidence_rows(pair):
    up = next(row for row in pair.rows if row.provider_event_id == "rating-up")
    late = next(row for row in pair.rows if row.provider_event_id == "rating-late")
    return (
        _row_evidence(up, security_id="security-meta", historical_ticker="FB"),
        _row_evidence(late, security_id="security-goog", historical_ticker="GOOG"),
    )


def _authority(pair=None, *, rows=None, sources=None):
    pair = pair or _pair()
    return build_production_evidence_authority(
        pair,
        source_bindings=sources or _sources(),
        row_evidence=_evidence_rows(pair) if rows is None else rows,
    )


def _replace_component(row: ProductionRowEvidence, component: str, **changes):
    value = getattr(row, component)
    assert value is not None
    return dataclasses.replace(row, **{component: dataclasses.replace(value, **changes)})


def _current_batch_for_row(row: ProductionRowEvidence, *, sources=None):
    pair = _pair()
    authority = _authority(pair, rows=(row,), sources=sources)
    return build_production_input_batch(
        authority, signal_arm=SignalArm.CURRENT_VINTAGE
    )


def _rating_up_admission(batch):
    return next(
        item
        for item in batch.admissions
        if item.source_locator.row_offset == 0
        and item.source_role is MassiveSourceRole.ANALYST_RATINGS
    )


def test_static_contract_binds_c1_and_keeps_every_external_capability_closed():
    record = production_input_contract_record()
    assert sha256_bytes(render_production_input_contract_bytes()) == PRODUCTION_INPUT_CONTRACT_SHA256
    assert PRODUCTION_INPUT_CONTRACT_ID.endswith(PRODUCTION_INPUT_CONTRACT_SHA256[:16])
    assert record["parent"]["contract_sha256"] == (
        "b2b78be3e11a8c0f7995af6a14f819a1bc5283ca1c51638e9e92130590c6b4b0"
    )
    assert record["source_role_is_signal_arm"] is False
    assert record["accepted_risk"]["pristine_point_in_time"] is False
    assert set(record["external_bindings"].values()) == {None}
    assert set(record["capabilities"].values()) == {False}


def test_current_and_censored_arms_share_pair_but_have_distinct_exact_censuses():
    authority = _authority()
    current = build_production_input_batch(
        authority, signal_arm=SignalArm.CURRENT_VINTAGE
    )
    censored = build_production_input_batch(
        authority, signal_arm=SignalArm.CONSERVATIVE_CENSORED
    )
    assert require_production_evidence_authority(authority) is authority
    assert require_production_input_batch(current) is current
    assert require_production_input_batch(censored) is censored
    assert current.total_source_row_count == censored.total_source_row_count == 6
    assert current.directional_candidate_count == current.normalized_row_count == 2
    assert censored.directional_candidate_count == censored.normalized_row_count == 1
    assert current.batch_sha256 != censored.batch_sha256
    assert len(current.admissions) == len(authority.pair.rows)
    assert [item.source_locator for item in current.admissions] == [
        row.locator for row in authority.pair.rows
    ]
    assert current.source_role_separate_from_signal_arm is True
    assert {row.source_role for row in current.normalized_rows} == {
        MassiveSourceRole.ANALYST_RATINGS
    }
    assert {row.signal_arm for row in current.normalized_rows} == {
        SignalArm.CURRENT_VINTAGE
    }
    late = next(
        item
        for item in censored.admissions
        if item.source_locator.row_offset == 1
    )
    assert late.disposition is AdmissionDisposition.SOURCE_VIEW_EXCLUDED


def test_normalized_row_uses_permanent_identity_exact_scores_and_no_price_or_outcome():
    batch = build_production_input_batch(
        _authority(), signal_arm=SignalArm.CURRENT_VINTAGE
    )
    row = next(item for item in batch.normalized_rows if item.provider_event_id == "rating-up")
    assert row.current_restated_ticker == "META"
    assert row.historical_ticker == "FB"
    assert row.security_id == "security-meta"
    assert row.publication_at_utc == "2020-01-02T09:31:00.000000Z"
    assert row.rating_change == Fraction(2)
    assert row.q_data == Decimal("0.875")
    assert row.pristine_point_in_time is False
    assert row.row_sha256 == sha256_bytes(canonical_json_bytes(row.semantic_record()))
    field_names = {field.name for field in dataclasses.fields(NormalizedPreOutcomeRow)}
    assert not any("price" in name or "outcome" in name for name in field_names)


def test_missing_publication_time_is_retained_as_null_for_later_named_refusal():
    pair = _pair(ratings=[_rating_row("rating-up", time=None)])
    source = next(
        row for row in pair.rows if row.provider_event_id == "rating-up"
    )
    batch = build_production_input_batch(
        _authority(
            pair,
            rows=(
                _row_evidence(
                    source,
                    security_id="security-meta",
                    historical_ticker="FB",
                ),
            ),
        ),
        signal_arm=SignalArm.CURRENT_VINTAGE,
    )
    assert len(batch.normalized_rows) == 1
    assert batch.normalized_rows[0].publication_at_utc is None


def test_publication_clock_tamper_is_content_and_semantically_refused():
    batch = build_production_input_batch(
        _authority(), signal_arm=SignalArm.CURRENT_VINTAGE
    )
    row = batch.normalized_rows[0]
    with pytest.raises(ProductionInputError):
        dataclasses.replace(row, publication_at_utc="2020-01-03T09:31:00.000000Z")


def test_every_non_signal_row_gets_a_specific_terminal_disposition():
    batch = build_production_input_batch(
        _authority(), signal_arm=SignalArm.CURRENT_VINTAGE
    )
    by_offset = {
        (item.source_role, item.source_locator.row_offset): item.disposition
        for item in batch.admissions
    }
    assert by_offset[(MassiveSourceRole.ANALYST_RATINGS, 2)] is (
        AdmissionDisposition.NON_DIRECTIONAL_RATING_ACTION
    )
    assert by_offset[(MassiveSourceRole.ANALYST_RATINGS, 3)] is (
        AdmissionDisposition.PRE_2013_QUARANTINED
    )
    assert by_offset[(MassiveSourceRole.EARNINGS, 0)] is (
        AdmissionDisposition.NON_RATING_SOURCE_ROLE
    )
    assert by_offset[(MassiveSourceRole.CORPORATE_GUIDANCE, 0)] is (
        AdmissionDisposition.GUIDANCE_CLOCK_QUARANTINED
    )
    assert all(item.terminal_sha256 == item.derived_sha256 for item in batch.admissions)


def test_missing_row_evidence_is_named_and_makes_directional_census_incomplete():
    pair = _pair()
    authority = _authority(pair, rows=_evidence_rows(pair)[1:])
    batch = build_production_input_batch(
        authority, signal_arm=SignalArm.CURRENT_VINTAGE
    )
    admission = _rating_up_admission(batch)
    assert admission.disposition is AdmissionDisposition.MISSING_ROW_EVIDENCE
    assert batch.normalized_row_count == 1
    assert batch.refused_directional_count == 1
    assert batch.all_directional_rows_admitted is False
    assert batch.formal_backtest_input_ready is False


def test_duplicate_or_out_of_scope_row_evidence_is_refused_before_composition():
    pair = _pair()
    rows = _evidence_rows(pair)
    with pytest.raises(ProductionInputError, match="duplicate"):
        _authority(pair, rows=(rows[0], rows[0]))
    old = next(row for row in pair.rows if row.provider_event_id == "rating-old")
    with pytest.raises(ProductionInputError, match="excluded or non-rating"):
        _authority(
            pair,
            rows=(
                *rows,
                dataclasses.replace(rows[0], locator=old.locator),
            ),
        )


def test_source_inventory_is_exhaustive_ordered_and_component_bound():
    pair = _pair()
    rows = _evidence_rows(pair)
    with pytest.raises(ProductionInputError, match="every evidence kind"):
        _authority(pair, sources=_sources()[:-1])
    with pytest.raises(ProductionInputError, match="canonical order"):
        _authority(pair, sources=tuple(reversed(_sources())))
    mismatched = _replace_component(rows[0], "common_event", source_sha256="f" * 64)
    with pytest.raises(ProductionInputError, match="common_event evidence source"):
        _authority(pair, rows=(mismatched, rows[1]))


@pytest.mark.parametrize(
    ("component", "changes", "expected"),
    [
        ("security", {"current_ticker_only": True}, AdmissionDisposition.SECURITY_IDENTITY_CURRENT_TICKER_ONLY),
        ("security", {"point_in_time": False}, AdmissionDisposition.SECURITY_IDENTITY_NOT_PIT),
        ("security", {"candidate_count": 2}, AdmissionDisposition.SECURITY_IDENTITY_AMBIGUOUS),
        ("security", {"provider_event_id": "wrong-event"}, AdmissionDisposition.SECURITY_IDENTITY_MISMATCH),
        ("security", {"available_at": CUTOFF}, AdmissionDisposition.SECURITY_IDENTITY_LATE),
        ("firm", {"ontology_reviewed": False}, AdmissionDisposition.FIRM_ONTOLOGY_UNREVIEWED),
        ("firm", {"labels_reviewed": False}, AdmissionDisposition.FIRM_LABEL_UNREVIEWED),
        ("firm", {"candidate_count": 2}, AdmissionDisposition.FIRM_MAPPING_AMBIGUOUS),
        ("firm", {"raw_current_label": "Strong Buy"}, AdmissionDisposition.FIRM_MAPPING_MISMATCH),
        ("firm", {"available_at": CUTOFF}, AdmissionDisposition.FIRM_MAPPING_LATE),
        ("firm", {"current_score": Fraction(-1), "previous_score": Fraction(1)}, AdmissionDisposition.RATING_DIRECTION_MISMATCH),
        ("common_event", {"candidate_count": 2}, AdmissionDisposition.COMMON_EVENT_AMBIGUOUS),
        ("common_event", {"provider_event_id": "wrong-event"}, AdmissionDisposition.COMMON_EVENT_MISMATCH),
        ("common_event", {"available_at": CUTOFF}, AdmissionDisposition.COMMON_EVENT_LATE),
        ("sector", {"candidate_count": 2}, AdmissionDisposition.SECTOR_AMBIGUOUS),
        ("sector", {"point_in_time": False}, AdmissionDisposition.SECTOR_NOT_PIT),
        ("sector", {"security_id": "wrong-security"}, AdmissionDisposition.SECTOR_MISMATCH),
        ("sector", {"available_at": CUTOFF}, AdmissionDisposition.SECTOR_LATE),
        ("control", {"contains_outcome_or_price": True}, AdmissionDisposition.CONTROL_CONTAINS_OUTCOME_OR_PRICE),
        ("control", {"point_in_time": False}, AdmissionDisposition.CONTROL_NOT_PIT),
        ("control", {"complete": False}, AdmissionDisposition.CONTROL_MISMATCH),
        ("control", {"available_at": CUTOFF}, AdmissionDisposition.CONTROL_LATE),
        ("q_data", {"point_in_time": False}, AdmissionDisposition.Q_DATA_NOT_PIT),
        ("q_data", {"security_id": "wrong-security"}, AdmissionDisposition.Q_DATA_MISMATCH),
        ("q_data", {"available_at": CUTOFF}, AdmissionDisposition.Q_DATA_LATE),
    ],
)
def test_hostile_or_incomplete_evidence_fails_closed_with_named_disposition(
    component, changes, expected
):
    pair = _pair()
    row = _replace_component(_evidence_rows(pair)[0], component, **changes)
    batch = _current_batch_for_row(row)
    admission = _rating_up_admission(batch)
    assert admission.disposition is expected
    assert admission.normalized_row is None


@pytest.mark.parametrize(
    ("component", "expected"),
    [
        ("security", AdmissionDisposition.MISSING_PIT_SECURITY_EVIDENCE),
        ("firm", AdmissionDisposition.MISSING_FIRM_ONTOLOGY_EVIDENCE),
        ("common_event", AdmissionDisposition.MISSING_COMMON_EVENT_EVIDENCE),
        ("sector", AdmissionDisposition.MISSING_PIT_SECTOR_EVIDENCE),
        ("control", AdmissionDisposition.MISSING_PREOPEN_CONTROL_EVIDENCE),
        ("q_data", AdmissionDisposition.MISSING_Q_DATA_EVIDENCE),
    ],
)
def test_each_missing_evidence_family_has_a_named_refusal(component, expected):
    pair = _pair()
    row = dataclasses.replace(_evidence_rows(pair)[0], **{component: None})
    batch = _current_batch_for_row(row)
    assert _rating_up_admission(batch).disposition is expected


def test_unreviewed_or_non_pit_source_binding_refuses_without_self_promotion():
    pair = _pair()
    row = _evidence_rows(pair)[0]
    firm_unreviewed = _sources(
        changed_kind=EvidenceSourceKind.FIRM_ONTOLOGY, reviewed=False
    )
    batch = _current_batch_for_row(row, sources=firm_unreviewed)
    assert _rating_up_admission(batch).disposition is (
        AdmissionDisposition.FIRM_ONTOLOGY_UNREVIEWED
    )
    sector_non_pit = _sources(
        changed_kind=EvidenceSourceKind.SECTOR_CLASSIFICATION,
        point_in_time=False,
    )
    batch = _current_batch_for_row(row, sources=sector_non_pit)
    assert _rating_up_admission(batch).disposition is (
        AdmissionDisposition.NON_PIT_EVIDENCE_SOURCE
    )
    assert batch.production_input_authority is False


def test_unknown_provider_field_or_invalid_directional_row_never_reaches_normalization():
    pair = _pair(ratings=[_rating_row("rating-up", surprise_outcome="forbidden")])
    authority = _authority(pair, rows=())
    batch = build_production_input_batch(
        authority, signal_arm=SignalArm.CURRENT_VINTAGE
    )
    assert _rating_up_admission(batch).disposition is (
        AdmissionDisposition.UNSUPPORTED_RATING_ROW_SCHEMA
    )
    pair = _pair(ratings=[_rating_row("rating-up", previous_rating="")])
    authority = _authority(pair, rows=())
    batch = build_production_input_batch(
        authority, signal_arm=SignalArm.CURRENT_VINTAGE
    )
    assert _rating_up_admission(batch).disposition is AdmissionDisposition.INVALID_RATING_ROW


@pytest.mark.parametrize(
    "changes",
    [
        {"price_target": "12.5"},
        {"importance": True},
        {"rating": "BUY", "previous_rating": "buy"},
        {"last_updated": "2020-01-01T12:00:00Z"},
        {"last_updated": 1},
        {"last_updated": True},
        {"last_updated": {}},
        {"last_updated": []},
        {"last_updated": "2020-01-03T12:00:00"},
    ],
)
def test_provider_values_incompatible_with_rating_ingest_are_not_normalized(changes):
    pair = _pair(ratings=[_rating_row("rating-up", **changes)])
    authority = _authority(pair, rows=())
    batch = build_production_input_batch(
        authority, signal_arm=SignalArm.CURRENT_VINTAGE
    )
    assert _rating_up_admission(batch).disposition is (
        AdmissionDisposition.INVALID_RATING_ROW
    )


def test_c2_refuses_naive_last_updated_in_both_pre_score_arms():
    pair = _pair(ratings=[_rating_row("rating-up", last_updated="2020-01-03T12:00:00")])
    source = pair.rows[0]
    evidence = _row_evidence(source, security_id="security-meta", historical_ticker="FB")
    authority = _authority(pair, rows=(evidence,))
    current = build_production_input_batch(authority, signal_arm=SignalArm.CURRENT_VINTAGE)
    censored = build_production_input_batch(
        authority, signal_arm=SignalArm.CONSERVATIVE_CENSORED
    )
    assert current.normalized_row_count == 0
    assert current.admissions[0].disposition is AdmissionDisposition.INVALID_RATING_ROW
    assert current.directional_candidate_count == 1
    assert current.refused_directional_count == 1
    assert current.all_directional_rows_admitted is False
    assert censored.normalized_row_count == 0
    assert censored.admissions[0].disposition is AdmissionDisposition.SOURCE_VIEW_EXCLUDED
    assert current.pristine_point_in_time is False


def test_malformed_unknown_and_unsupported_actions_are_potential_directional_refusals():
    pair = _pair(
        ratings=[
            _rating_row("valid"),
            _rating_row("malformed", previous_rating=""),
            _rating_row("unknown", action="future_provider_action"),
            _rating_row("unsupported", action="assumes"),
            _rating_row(
                "maintain",
                action="maintains",
                rating="Buy",
                previous_rating="Buy",
            ),
        ]
    )
    valid_source = next(row for row in pair.rows if row.provider_event_id == "valid")
    authority = _authority(
        pair,
        rows=(
            _row_evidence(
                valid_source,
                security_id="security-valid",
                historical_ticker="META",
            ),
        ),
    )
    batch = build_production_input_batch(
        authority, signal_arm=SignalArm.CURRENT_VINTAGE
    )
    by_id = {
        source.provider_event_id: admission
        for source, admission in zip(pair.rows, batch.admissions, strict=True)
        if source.locator.source_role is MassiveSourceRole.ANALYST_RATINGS
    }
    assert by_id["malformed"].disposition is AdmissionDisposition.INVALID_RATING_ROW
    assert by_id["unknown"].disposition is AdmissionDisposition.UNKNOWN_RATING_ACTION
    assert by_id["unsupported"].disposition is (
        AdmissionDisposition.UNSUPPORTED_RATING_ACTION
    )
    assert by_id["maintain"].disposition is (
        AdmissionDisposition.NON_DIRECTIONAL_RATING_ACTION
    )
    assert all(
        by_id[event_id].potential_directional
        for event_id in ("valid", "malformed", "unknown", "unsupported")
    )
    assert by_id["maintain"].potential_directional is False
    assert batch.directional_candidate_count == 4
    assert batch.normalized_row_count == 1
    assert batch.refused_directional_count == 3
    assert batch.all_directional_rows_admitted is False


@pytest.mark.parametrize(
    ("component", "valid_to"),
    [
        ("security", "2020-01-02"),
        ("firm", "2020-01-02"),
        ("sector", "2020-01-06"),
    ],
)
def test_interval_closure_is_applied_only_when_available_before_cutoff(
    component, valid_to
):
    pair = _pair()
    original = _evidence_rows(pair)[0]
    hidden_closure = _replace_component(
        original,
        component,
        valid_to=valid_to,
        valid_to_available_at=CUTOFF,
    )
    hidden_batch = _current_batch_for_row(hidden_closure)
    assert _rating_up_admission(hidden_batch).disposition is (
        AdmissionDisposition.INCLUDED_DIRECTIONAL_RATING_REVISION
    )

    visible_closure = _replace_component(
        original,
        component,
        valid_to=valid_to,
        valid_to_available_at="2020-01-06T14:29:30.000000Z",
    )
    visible_batch = _current_batch_for_row(visible_closure)
    expected = {
        "security": AdmissionDisposition.SECURITY_IDENTITY_MISMATCH,
        "firm": AdmissionDisposition.FIRM_MAPPING_MISMATCH,
        "sector": AdmissionDisposition.SECTOR_MISMATCH,
    }[component]
    assert _rating_up_admission(visible_batch).disposition is expected

    with pytest.raises(ProductionInputError, match="closure availability"):
        _replace_component(original, component, valid_to=valid_to)


def test_stale_q_data_is_not_an_event_level_score_input_and_daily_cross_sections_remain_required():
    pair = _pair()
    row = _replace_component(
        _evidence_rows(pair)[0],
        "q_data",
        measured_session="2020-01-03",
    )
    batch = _current_batch_for_row(row)
    assert _rating_up_admission(batch).disposition is AdmissionDisposition.Q_DATA_MISMATCH
    assert batch.event_level_only is True
    assert batch.decision_date_cross_sections_required is True
    assert batch.decision_date_cross_sections_bound is False
    assert batch.formal_backtest_input_ready is False

    admitted = build_production_input_batch(
        _authority(), signal_arm=SignalArm.CURRENT_VINTAGE
    ).normalized_rows[0]
    assert admitted.cross_section_evidence_scope == (
        "eligibility_session_audit_only_not_reusable_for_later_decision_sessions"
    )
    assert admitted.later_decision_date_cross_sections_bound is False


def _same_security_topology_rows():
    pair = _pair(
        ratings=[
            _rating_row("same-security-1"),
            _rating_row("same-security-2"),
        ]
    )
    first = _row_evidence(
        pair.rows[0], security_id="security-same", historical_ticker="FB"
    )
    second = _row_evidence(
        pair.rows[1], security_id="security-same", historical_ticker="FB"
    )
    assert first.security is not None and second.security is not None
    assert first.sector is not None and second.sector is not None
    assert first.control is not None and second.control is not None
    assert first.q_data is not None and second.q_data is not None
    second = dataclasses.replace(
        second,
        security=dataclasses.replace(
            second.security,
            mapping_evidence_sha256=first.security.mapping_evidence_sha256,
        ),
        sector=dataclasses.replace(
            second.sector,
            evidence_sha256=first.sector.evidence_sha256,
        ),
        control=dataclasses.replace(
            second.control,
            evidence_sha256=first.control.evidence_sha256,
            control_vector_sha256=first.control.control_vector_sha256,
        ),
        q_data=dataclasses.replace(
            second.q_data,
            evidence_sha256=first.q_data.evidence_sha256,
        ),
    )
    return pair, first, second


@pytest.mark.parametrize(
    ("component", "changes"),
    [
        ("security", {"historical_ticker": "META"}),
        ("firm", {"institution_id": "institution-conflict"}),
        ("sector", {"sector_id": "sector-conflict"}),
        ("control", {"industry_id": "industry-conflict"}),
        ("q_data", {"q_data": Decimal("0.125")}),
    ],
)
def test_conflicting_same_key_cross_row_facts_refuse_authority(component, changes):
    pair, first, second = _same_security_topology_rows()
    require_production_evidence_authority(
        _authority(pair, rows=(first, second))
    )
    changed = _replace_component(second, component, **changes)
    with pytest.raises(ProductionInputError, match="conflicting cross-row"):
        _authority(pair, rows=(first, changed))


def _different_date_lineage_rows(*, same_ticker: bool):
    pair = _pair(
        ratings=[
            _rating_row("lineage-1", event_date="2020-01-02", ticker="META"),
            _rating_row(
                "lineage-2",
                event_date="2020-01-03",
                ticker="META" if same_ticker else "GOOG",
            ),
        ]
    )
    first_source = next(
        row for row in pair.rows if row.provider_event_id == "lineage-1"
    )
    second_source = next(
        row for row in pair.rows if row.provider_event_id == "lineage-2"
    )
    first = _row_evidence(
        first_source,
        security_id="security-lineage-1",
        historical_ticker="FB",
    )
    second = _row_evidence(
        second_source,
        security_id="security-lineage-2",
        historical_ticker="FB" if same_ticker else "GOOG",
    )
    return pair, first, second


def test_overlapping_provider_firm_identity_lineage_is_globally_refused():
    pair, first, second = _different_date_lineage_rows(same_ticker=False)
    changed = _replace_component(
        second,
        "firm",
        institution_id="institution-conflict",
    )
    with pytest.raises(
        ProductionInputError,
        match="contradictory overlapping provider-firm identity lineage",
    ):
        _authority(pair, rows=(first, changed))

    assert first.firm is not None and changed.firm is not None
    closed_first = dataclasses.replace(
        first,
        firm=dataclasses.replace(
            first.firm,
            valid_to="2020-01-03",
            valid_to_available_at=EARLY,
        ),
    )
    successor = dataclasses.replace(
        changed,
        firm=dataclasses.replace(changed.firm, valid_from="2020-01-03"),
    )
    require_production_evidence_authority(
        _authority(pair, rows=(closed_first, successor))
    )


def test_overlapping_ticker_to_permanent_security_lineage_is_globally_refused():
    pair, first, second = _different_date_lineage_rows(same_ticker=True)
    with pytest.raises(
        ProductionInputError,
        match="contradictory overlapping security historical_ticker lineage",
    ):
        _authority(pair, rows=(first, second))

    assert first.security is not None and second.security is not None
    closed_first = dataclasses.replace(
        first,
        security=dataclasses.replace(
            first.security,
            valid_to="2020-01-03",
            valid_to_available_at=EARLY,
        ),
    )
    successor = dataclasses.replace(
        second,
        security=dataclasses.replace(second.security, valid_from="2020-01-03"),
    )
    require_production_evidence_authority(
        _authority(pair, rows=(closed_first, successor))
    )


def test_comparison_report_is_pre_return_exhaustive_and_dimension_complete():
    authority = _authority()
    report = build_production_input_comparison_report(authority)
    current = build_production_input_batch(
        authority, signal_arm=SignalArm.CURRENT_VINTAGE
    )
    censored = build_production_input_batch(
        authority, signal_arm=SignalArm.CONSERVATIVE_CENSORED
    )
    assert current.comparison_report == censored.comparison_report == report
    assert report.exhaustive is True
    assert report.pre_return is True
    assert report.outcome_access is False
    overall = report.breakdowns[0]
    assert overall.dimension is ComparisonDimension.OVERALL
    assert overall.total_count == 6
    assert overall.current_admitted_count == 2
    assert overall.current_refused_count == 4
    assert overall.censored_admitted_count == 1
    assert overall.censored_refused_count == 5
    assert overall.mapping_disagreement_count == 1
    assert overall.signal_disagreement_count == 1
    assert overall.signal_disagreement_rate.fraction == Fraction(1, 6)
    for dimension in ComparisonDimension:
        assert sum(
            item.total_count
            for item in report.breakdowns
            if item.dimension is dimension
        ) == report.breakdowns[0].total_count
    assert any(
        item.dimension is ComparisonDimension.FIRM
        and item.key == "institution-1"
        for item in report.breakdowns
    )
    assert any(
        item.dimension is ComparisonDimension.SECURITY
        and item.key == "security-meta"
        for item in report.breakdowns
    )


@pytest.mark.parametrize(
    "binding_name",
    [
        "_at_or_after_cutoff",
        "_validate_row_evidence_topology",
        "build_production_input_batch",
    ],
)
def test_local_callable_rebinding_is_detected_before_authority_reuse(binding_name):
    authority = _authority()
    original = getattr(pipeline_module, binding_name)
    setattr(pipeline_module, binding_name, lambda *args, **kwargs: None)
    try:
        with pytest.raises(ProductionInputError, match="static contract changed"):
            require_production_evidence_authority(authority)
    finally:
        setattr(pipeline_module, binding_name, original)


def test_pinned_guard_alias_and_dataclass_method_rebinding_refuse():
    authority = _authority()
    original_guard = pipeline_module._PINNED_REQUIRE_STATIC_CONTRACT
    pipeline_module._PINNED_REQUIRE_STATIC_CONTRACT = lambda: None
    try:
        with pytest.raises(ProductionInputError, match="static contract changed"):
            build_production_input_batch(
                authority, signal_arm=SignalArm.CURRENT_VINTAGE
            )
    finally:
        pipeline_module._PINNED_REQUIRE_STATIC_CONTRACT = original_guard

    original_method = pipeline_module.SecurityIdentityEvidence.to_record
    pipeline_module.SecurityIdentityEvidence.to_record = lambda self: {}
    try:
        with pytest.raises(ProductionInputError, match="static contract changed"):
            require_production_evidence_authority(authority)
    finally:
        pipeline_module.SecurityIdentityEvidence.to_record = original_method


def _clone(instance, cls):
    clone = object.__new__(cls)
    for field in dataclasses.fields(instance):
        object.__setattr__(clone, field.name, getattr(instance, field.name))
    return clone


def test_non_current_c1_authority_and_non_pristine_relabeling_are_rejected():
    pair = _pair()
    with pytest.raises(AcceptedRiskInputError, match="builder-authenticated"):
        _authority(_clone(pair, AcceptedRiskInputPair), rows=())
    object.__setattr__(pair, "pristine_point_in_time", True)
    with pytest.raises(AcceptedRiskInputError, match="changed after authentication"):
        _authority(pair, rows=())


def test_evidence_and_batch_clones_post_build_mutations_and_capability_flips_refuse():
    authority = _authority()
    with pytest.raises(ProductionInputError, match="builder-authenticated"):
        require_production_evidence_authority(
            _clone(authority, ProductionEvidenceAuthority)
        )
    batch = build_production_input_batch(
        authority, signal_arm=SignalArm.CURRENT_VINTAGE
    )
    with pytest.raises(ProductionInputError, match="builder-authenticated"):
        require_production_input_batch(_clone(batch, ProductionInputBatch))
    object.__setattr__(batch, "admissions", batch.admissions[:-1])
    with pytest.raises(ProductionInputError, match="changed after authentication"):
        require_production_input_batch(batch)

    fresh = build_production_input_batch(
        authority, signal_arm=SignalArm.CURRENT_VINTAGE
    )
    object.__setattr__(fresh, "outcome_access", True)
    with pytest.raises(ProductionInputError, match="forbidden capability"):
        require_production_input_batch(fresh)


def test_nested_authority_mutation_is_detected_before_reuse():
    authority = _authority()
    object.__setattr__(authority, "row_evidence", authority.row_evidence[:-1])
    with pytest.raises(ProductionInputError, match="changed after authentication"):
        require_production_evidence_authority(authority)


def test_hostile_nested_replacements_are_rejected_without_invocation():
    class Hostile:
        calls = 0

        def __getattribute__(self, name):
            if name != "calls":
                type(self).calls += 1
                raise AssertionError("hostile evidence was invoked")
            return object.__getattribute__(self, name)

    hostile = Hostile()
    authority = _authority()
    object.__setattr__(authority, "authority_id", hostile)
    with pytest.raises(ProductionInputError, match="must be an exact string"):
        require_production_evidence_authority(authority)
    assert Hostile.calls == 0

    authority = _authority()
    object.__setattr__(authority.row_evidence[0], "security", hostile)
    with pytest.raises(ProductionInputError, match="security evidence must have exact type"):
        require_production_evidence_authority(authority)
    assert Hostile.calls == 0

    authority = _authority()
    batch = build_production_input_batch(
        authority, signal_arm=SignalArm.CURRENT_VINTAGE
    )
    object.__setattr__(batch, "batch_id", hostile)
    with pytest.raises(ProductionInputError, match="must be an exact string"):
        require_production_input_batch(batch)
    assert Hostile.calls == 0

    batch = build_production_input_batch(
        authority, signal_arm=SignalArm.CURRENT_VINTAGE
    )
    object.__setattr__(batch, "admissions", (hostile, *batch.admissions[1:]))
    with pytest.raises(ProductionInputError, match="exact typed tuple"):
        require_production_input_batch(batch)
    assert Hostile.calls == 0


@pytest.mark.parametrize(
    "field",
    [
        "pristine_point_in_time",
        "earlier_version_imputation_performed",
        "production_input_authority",
        "formal_backtest_input_ready",
        "provider_access",
        "credential_access",
        "filesystem_access",
        "quantconnect_access",
        "object_store_access",
        "price_access",
        "outcome_access",
        "deployment",
        "orders",
        "trading",
    ],
)
def test_every_closed_batch_flag_is_independently_reauthenticated(field):
    batch = build_production_input_batch(
        _authority(), signal_arm=SignalArm.CURRENT_VINTAGE
    )
    object.__setattr__(batch, field, True)
    with pytest.raises(ProductionInputError, match="forbidden capability"):
        require_production_input_batch(batch)


def test_module_import_and_ast_surface_has_no_io_provider_qc_or_execution_path():
    path = Path("research/analyst_revisions_v2/production_input_pipeline.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    forbidden_import_fragments = {
        "requests",
        "urllib",
        "httpx",
        "socket",
        "subprocess",
        "pathlib",
        "quantconnect",
        "execution",
        "broker",
    }
    assert not {
        name
        for name in imports
        if any(fragment in name.casefold() for fragment in forbidden_import_fragments)
    }
    forbidden_calls = {
        "open",
        "read_text",
        "read_bytes",
        "write_text",
        "write_bytes",
        "getenv",
        "urlopen",
        "request",
    }
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    called.update(
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    )
    assert not called & forbidden_calls
