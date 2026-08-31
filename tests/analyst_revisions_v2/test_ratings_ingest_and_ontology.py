from __future__ import annotations

import dataclasses
from fractions import Fraction

import pytest

from research.analyst_revisions_v2.canonical import canonical_json_bytes
from research.analyst_revisions_v2.firm_ontology import (
    FIRM_ONTOLOGY_SCHEMA,
    FirmOntologyError,
    RatingMapping,
    RatingMappingRefusal,
    RatingMappingRefusalReason,
    ReviewedFirmRatingOntology,
    load_reviewed_firm_rating_ontology,
    resolve_firm_rating,
    revalidate_firm_rating_ontology,
)
from research.analyst_revisions_v2.ratings_ingest import (
    BENZINGA_PROVIDER_CONTRACT_ID,
    BENZINGA_PROVIDER_CONTRACT_SHA256,
    DailyDedupeRefusalReason,
    DailyRatingContributionCandidate,
    FirmNormalizationRefusal,
    FirmNormalizedRatingEvent,
    ProviderVersionChange,
    RatingAction,
    RatingsIngestError,
    RatingsIngestRefusalReason,
    TransitionRefusalReason,
    audit_benzinga_snapshot,
    benzinga_provider_contract_record,
    build_firm_rating_vocabulary,
    compare_benzinga_snapshot_lineage,
    deduplicate_daily_rating_contributions,
    normalize_firm_rating_event,
    normalize_firm_rating_audit,
    revalidate_firm_rating_normalization,
    revalidate_benzinga_ingest_audit,
)
from research.analyst_revisions_v2.snapshot import load_verified_snapshot

from ._helpers import FIXED_VERIFIED_AT, write_snapshot


EVIDENCE_HASH = "7" * 64


def _rating_row(
    row_id: str,
    *,
    year: int = 2020,
    firm_id: str = "firm-1",
    firm: str = "Broker One",
    analyst_id: str | None = "analyst-1",
    analyst: str | None = "Analyst One",
    action: str | None = "upgrades",
    rating: str | None = "Buy",
    previous_rating: str | None = "Hold",
    ticker: str = "AAA",
    last_updated: str | None = None,
) -> dict:
    row = {
        "event_year": year,
        "benzinga_id": row_id,
        "benzinga_firm_id": firm_id,
        "firm": firm,
        "benzinga_analyst_id": analyst_id,
        "analyst": analyst,
        "date": f"{year:04d}-01-02",
        "time": "09:31:02",
        "last_updated": (
            last_updated or f"{year:04d}-01-02T15:01:03Z"
        ),
        "rating_action": action,
        "rating": rating,
        "previous_rating": previous_rating,
        "ticker": ticker,
    }
    return {key: value for key, value in row.items() if value is not None}


def _benzinga_snapshot(
    root,
    rows,
    *,
    year: int = 2020,
    snapshot_id: str = "benzinga-snapshot-1",
    captured_at: str = "2026-08-26T11:00:00.000000Z",
):
    write_snapshot(
        root,
        rows_by_year={year: rows},
        snapshot_id=snapshot_id,
        provider_contract_id=BENZINGA_PROVIDER_CONTRACT_ID,
        provider_contract_sha256=BENZINGA_PROVIDER_CONTRACT_SHA256,
        captured_at=captured_at,
    )
    return load_verified_snapshot(
        root, verified_at="2026-08-28T12:00:00.000000Z"
    )


def _entry(
    label: str,
    rank: int,
    size: int,
    *,
    firm_id: str = "firm-1",
    valid_from: str = "2019-01-01",
    valid_to: str | None = "2022-01-01",
    scope: str = "absolute",
    quality: str = "reviewed_primary",
):
    return {
        "provider_firm_id": firm_id,
        "firm_name": f"Broker {firm_id}",
        "valid_from": valid_from,
        "valid_to": valid_to,
        "raw_label": label,
        "ordered_rank": rank,
        "scale_size": size,
        "scope": scope,
        "mapping_quality": quality,
        "reviewer": "Independent Reviewer",
        "source_evidence_id": f"evidence-{firm_id}-{rank}-{label.lower().replace(' ', '-')}",
        "source_evidence_sha256": EVIDENCE_HASH,
    }


def _ontology_payload(entries):
    return {
        "schema": FIRM_ONTOLOGY_SCHEMA,
        "ontology_id": "ontology-fixture-1",
        "version": "version-1",
        "status": "reviewed",
        "reviewed_at": "2026-08-26T12:00:00.000000Z",
        "entries": entries,
    }


def _write_ontology(path, entries):
    path.write_bytes(canonical_json_bytes(_ontology_payload(entries)))
    return load_reviewed_firm_rating_ontology(path)


def _three_level_entries():
    return [
        _entry("Sell", 1, 3),
        _entry("Hold", 2, 3),
        _entry("Buy", 3, 3),
    ]


def test_provider_contract_is_content_addressed_and_snapshot_bound(tmp_path):
    contract = benzinga_provider_contract_record()
    assert contract["unknown_field_policy"] == "refuse_row"
    assert contract["rating_action_map"]["initiates_coverage_on"] == "initiation"
    assert contract["unsupported_documented_actions"] == ["assumes"]
    assert BENZINGA_PROVIDER_CONTRACT_SHA256 == (
        "2e7aa5584765ea5b3cdb40d8895cb852dbb62b43172de42adfb1d58bc0a12dbc"
    )
    snapshot = _benzinga_snapshot(
        tmp_path / "valid", [_rating_row("event-1")]
    )
    audit = audit_benzinga_snapshot(snapshot)
    assert len(audit.records) == 1
    assert not audit.refusals
    assert revalidate_benzinga_ingest_audit(audit) is audit

    wrong_root = write_snapshot(
        tmp_path / "wrong",
        rows_by_year={2020: [_rating_row("event-1")]},
    )
    wrong = load_verified_snapshot(wrong_root, verified_at=FIXED_VERIFIED_AT)
    with pytest.raises(RatingsIngestError, match="provider contract"):
        audit_benzinga_snapshot(wrong)


def test_documented_sample_shape_maps_action_and_conservative_clock(tmp_path):
    row = _rating_row(
        "event-1",
        action="maintains",
        rating="Neutral",
        previous_rating="Neutral",
        last_updated="2020-01-03T01:02:03-05:00",
    )
    row.update(
        {
            "adjusted_price_target": 15,
            "previous_adjusted_price_target": 13,
            "currency": "USD",
            "importance": 0,
            "price_target_action": "raises",
        }
    )
    audit = audit_benzinga_snapshot(
        _benzinga_snapshot(tmp_path / "snapshot", [row])
    )
    record = audit.records[0]
    assert record.action is RatingAction.MAINTAIN
    assert record.last_updated_at == "2020-01-03T06:02:03.000000Z"
    assert record.conservative_public_date == "2020-01-03"
    assert record.price_target_action == "raises"
    assert record.provider_version_id.endswith(record.source_locator.raw_row_sha256)


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("unknown_field", RatingsIngestRefusalReason.UNSUPPORTED_PROVIDER_SCHEMA),
        ("missing_event_id", RatingsIngestRefusalReason.MISSING_PROVIDER_EVENT_ID),
        ("missing_firm_id", RatingsIngestRefusalReason.MISSING_PROVIDER_FIRM_ID),
        ("missing_firm", RatingsIngestRefusalReason.MISSING_FIRM_NAME),
        ("invalid_date", RatingsIngestRefusalReason.INVALID_ACTION_DATE),
        ("invalid_update", RatingsIngestRefusalReason.INVALID_LAST_UPDATED),
        ("reverse_update", RatingsIngestRefusalReason.LAST_UPDATED_BEFORE_ACTION),
        ("invalid_ticker", RatingsIngestRefusalReason.INVALID_TICKER),
        ("missing_action", RatingsIngestRefusalReason.MISSING_RATING_ACTION),
        ("assumes", RatingsIngestRefusalReason.UNSUPPORTED_RATING_ACTION),
        ("uppercase_action", RatingsIngestRefusalReason.UNSUPPORTED_RATING_ACTION),
        ("missing_rating", RatingsIngestRefusalReason.MISSING_CURRENT_RATING),
        ("missing_previous", RatingsIngestRefusalReason.MISSING_PREVIOUS_RATING),
        (
            "self_transition",
            RatingsIngestRefusalReason.INCONSISTENT_RATING_TRANSITION,
        ),
        ("bad_importance", RatingsIngestRefusalReason.INVALID_PROVIDER_FIELD),
    ],
)
def test_every_structural_defect_has_one_named_refusal(tmp_path, mutation, reason):
    row = _rating_row("event-1")
    if mutation == "unknown_field":
        row["surprise_new_field"] = "value"
    elif mutation == "missing_event_id":
        row.pop("benzinga_id")
    elif mutation == "missing_firm_id":
        row.pop("benzinga_firm_id")
    elif mutation == "missing_firm":
        row.pop("firm")
    elif mutation == "invalid_date":
        row["date"] = "2020-02-30"
    elif mutation == "invalid_update":
        row["last_updated"] = "2020-01-02 15:00:00"
    elif mutation == "reverse_update":
        row["last_updated"] = "2020-01-01T15:00:00Z"
    elif mutation == "invalid_ticker":
        row["ticker"] = "aaa"
    elif mutation == "missing_action":
        row.pop("rating_action")
    elif mutation == "assumes":
        row["rating_action"] = "assumes"
    elif mutation == "uppercase_action":
        row["rating_action"] = "Upgrades"
    elif mutation == "missing_rating":
        row.pop("rating")
    elif mutation == "missing_previous":
        row.pop("previous_rating")
    elif mutation == "self_transition":
        row["rating"] = row["previous_rating"]
    else:
        row["importance"] = True
    audit = audit_benzinga_snapshot(
        _benzinga_snapshot(tmp_path / mutation, [row])
    )
    assert not audit.records
    assert len(audit.refusals) == 1
    assert audit.refusals[0].reason is reason


def test_target_only_is_separate_and_pre_2013_is_quarantined(tmp_path):
    target_only = _rating_row(
        "target-1", action=None, rating=None, previous_rating=None
    )
    target_only["price_target_action"] = "raises"
    audit = audit_benzinga_snapshot(
        _benzinga_snapshot(tmp_path / "target", [target_only])
    )
    assert audit.records[0].action is RatingAction.TARGET_ONLY

    early = _rating_row("early-1", year=2012)
    early_audit = audit_benzinga_snapshot(
        _benzinga_snapshot(tmp_path / "early", [early], year=2012)
    )
    assert early_audit.refusals[0].reason is (
        RatingsIngestRefusalReason.PROVIDER_BACKFILL_SEMANTICS_UNVERIFIED_PRE_2013
    )

    malformed_early = _rating_row("early-2", year=2012)
    malformed_early.pop("benzinga_id")
    malformed_audit = audit_benzinga_snapshot(
        _benzinga_snapshot(
            tmp_path / "malformed-early", [malformed_early], year=2012
        )
    )
    assert malformed_audit.refusals[0].reason is (
        RatingsIngestRefusalReason.PROVIDER_BACKFILL_SEMANTICS_UNVERIFIED_PRE_2013
    )


def test_vocabulary_inventory_preserves_firm_ids_names_counts_and_labels(tmp_path):
    first = _rating_row("event-1")
    second = _rating_row(
        "event-2", firm="Broker One Renamed", rating="Strong Buy"
    )
    audit = audit_benzinga_snapshot(
        _benzinga_snapshot(tmp_path / "vocabulary", [first, second])
    )
    vocabulary = build_firm_rating_vocabulary(audit)
    by_label = {entry.raw_label: entry for entry in vocabulary}
    assert by_label["Hold"].previous_count == 2
    assert by_label["Buy"].current_count == 1
    assert by_label["Strong Buy"].current_count == 1
    assert by_label["Hold"].raw_firm_names == (
        "Broker One",
        "Broker One Renamed",
    )


@pytest.mark.parametrize(
    ("conflicting", "reason"),
    [
        (False, RatingsIngestRefusalReason.DUPLICATE_PROVIDER_EVENT_ID),
        (True, RatingsIngestRefusalReason.CONFLICTING_PROVIDER_EVENT_VERSION),
    ],
)
def test_every_duplicate_provider_id_occurrence_is_refused(
    tmp_path, conflicting, reason
):
    first = _rating_row("duplicate-1")
    second = dict(first)
    if conflicting:
        second["rating"] = "Strong Buy"
    audit = audit_benzinga_snapshot(
        _benzinga_snapshot(tmp_path / str(conflicting), [first, second])
    )
    assert not audit.records
    assert len(audit.refusals) == 2
    assert {refusal.reason for refusal in audit.refusals} == {reason}
    assert len({refusal.evidence_sha256 for refusal in audit.refusals}) == 2


def test_ingest_audit_cannot_be_relabelled_or_drop_a_row(tmp_path):
    audit = audit_benzinga_snapshot(
        _benzinga_snapshot(
            tmp_path / "snapshot",
            [_rating_row("event-1"), _rating_row("event-2")],
        )
    )
    with pytest.raises(RatingsIngestError, match="exactly one"):
        dataclasses.replace(audit, records=audit.records[:1])
    relabelled = dataclasses.replace(
        audit.records[0], current_rating="Caller Selected Rating"
    )
    forged = dataclasses.replace(
        audit, records=(relabelled, audit.records[1])
    )
    with pytest.raises(RatingsIngestError, match="source-derived"):
        revalidate_benzinga_ingest_audit(forged)


def test_snapshot_lineage_distinguishes_corrections_additions_and_missing_rows(
    tmp_path,
):
    older = audit_benzinga_snapshot(
        _benzinga_snapshot(
            tmp_path / "older",
            [_rating_row("same-1"), _rating_row("corrected-1"), _rating_row("gone-1")],
            snapshot_id="snapshot-older",
            captured_at="2026-08-20T12:00:00.000000Z",
        )
    )
    corrected = _rating_row("corrected-1", rating="Strong Buy")
    newer = audit_benzinga_snapshot(
        _benzinga_snapshot(
            tmp_path / "newer",
            [_rating_row("same-1"), corrected, _rating_row("added-1")],
            snapshot_id="snapshot-newer",
            captured_at="2026-08-27T12:00:00.000000Z",
        )
    )
    lineage = compare_benzinga_snapshot_lineage(older, newer)
    changes = {entry.provider_event_id: entry.change for entry in lineage.entries}
    assert changes == {
        "added-1": ProviderVersionChange.ADDED_IN_LATER_SNAPSHOT,
        "corrected-1": ProviderVersionChange.CORRECTED_IN_LATER_SNAPSHOT,
        "gone-1": ProviderVersionChange.MISSING_FROM_LATER_SNAPSHOT,
        "same-1": ProviderVersionChange.UNCHANGED,
    }
    missing = next(entry for entry in lineage.entries if entry.provider_event_id == "gone-1")
    assert missing.newer_version_id is None
    assert missing.change.value == "missing_from_later_snapshot_not_withdrawal"

    with pytest.raises(RatingsIngestError, match="chronologically"):
        compare_benzinga_snapshot_lineage(newer, older)


def test_ontology_implements_exact_three_and_five_level_blueprint_scales(tmp_path):
    entries = _three_level_entries() + [
        _entry("Strong Sell", 1, 5, firm_id="firm-2"),
        _entry("Sell", 2, 5, firm_id="firm-2"),
        _entry("Hold", 3, 5, firm_id="firm-2"),
        _entry("Buy", 4, 5, firm_id="firm-2"),
        _entry("Strong Buy", 5, 5, firm_id="firm-2"),
    ]
    ontology = _write_ontology(tmp_path / "ontology.json", entries)
    three = [
        resolve_firm_rating(
            ontology,
            provider_firm_id="firm-1",
            event_date="2020-01-02",
            raw_label=label,
        )
        for label in ("Sell", "Hold", "Buy")
    ]
    five = [
        resolve_firm_rating(
            ontology,
            provider_firm_id="firm-2",
            event_date="2020-01-02",
            raw_label=label,
        )
        for label in ("Strong Sell", "Sell", "Hold", "Buy", "Strong Buy")
    ]
    assert all(isinstance(item, RatingMapping) for item in three + five)
    assert [item.score for item in three] == [Fraction(-1), Fraction(0), Fraction(1)]
    assert [item.score for item in five] == [
        Fraction(-1),
        Fraction(-1, 2),
        Fraction(0),
        Fraction(1, 2),
        Fraction(1),
    ]


def test_ambiguous_labels_and_missing_firm_periods_refuse_without_global_map(tmp_path):
    ontology = _write_ontology(tmp_path / "ontology.json", _three_level_entries())
    unknown = resolve_firm_rating(
        ontology,
        provider_firm_id="firm-1",
        event_date="2020-01-02",
        raw_label="Positive",
    )
    missing_firm = resolve_firm_rating(
        ontology,
        provider_firm_id="firm-9",
        event_date="2020-01-02",
        raw_label="Buy",
    )
    assert isinstance(unknown, RatingMappingRefusal)
    assert unknown.reason is RatingMappingRefusalReason.UNREVIEWED_RATING_LABEL
    assert isinstance(missing_firm, RatingMappingRefusal)
    assert missing_firm.reason is RatingMappingRefusalReason.NO_ACTIVE_FIRM_SCALE
    unreviewed_case_alias = resolve_firm_rating(
        ontology,
        provider_firm_id="firm-1",
        event_date="2020-01-02",
        raw_label="buy",
    )
    assert isinstance(unreviewed_case_alias, RatingMappingRefusal)
    assert unreviewed_case_alias.reason is (
        RatingMappingRefusalReason.UNREVIEWED_RATING_LABEL
    )


@pytest.mark.parametrize(
    "mutation",
    ["unsorted", "missing_rank", "duplicate_label", "overlap", "unreviewed"],
)
def test_ontology_structure_and_review_state_are_fail_closed(tmp_path, mutation):
    entries = _three_level_entries()
    payload = _ontology_payload(entries)
    if mutation == "unsorted":
        payload["entries"] = list(reversed(entries))
    elif mutation == "missing_rank":
        payload["entries"] = [entries[0], entries[2]]
    elif mutation == "duplicate_label":
        payload["entries"][1]["raw_label"] = "sell"
    elif mutation == "overlap":
        payload["entries"].extend(
            [
                _entry("Sell", 1, 3, valid_from="2021-01-01", valid_to=None),
                _entry("Hold", 2, 3, valid_from="2021-01-01", valid_to=None),
                _entry("Buy", 3, 3, valid_from="2021-01-01", valid_to=None),
            ]
        )
        payload["entries"] = sorted(
            payload["entries"],
            key=lambda item: (
                item["provider_firm_id"],
                item["valid_from"],
                item["valid_to"] or "9999-12-31",
                item["ordered_rank"],
                item["raw_label"].casefold(),
                item["raw_label"],
            ),
        )
    else:
        payload["status"] = "candidate"
    path = tmp_path / f"{mutation}.json"
    path.write_bytes(canonical_json_bytes(payload))
    with pytest.raises(FirmOntologyError):
        load_reviewed_firm_rating_ontology(path)


def test_ontology_authority_cannot_be_cloned_or_changed_after_loading(tmp_path):
    path = tmp_path / "ontology.json"
    ontology = _write_ontology(path, _three_level_entries())
    clone = object.__new__(ReviewedFirmRatingOntology)
    for field in dataclasses.fields(ontology):
        object.__setattr__(clone, field.name, getattr(ontology, field.name))
    with pytest.raises(FirmOntologyError, match="loader-authenticated"):
        revalidate_firm_rating_ontology(clone)

    payload = _ontology_payload(_three_level_entries())
    payload["version"] = "version-2"
    path.write_bytes(canonical_json_bytes(payload))
    with pytest.raises(FirmOntologyError, match="hash changed"):
        revalidate_firm_rating_ontology(ontology)


def test_only_reviewed_firm_order_can_create_a_genuine_rating_change(tmp_path):
    ontology = _write_ontology(tmp_path / "ontology.json", _three_level_entries())
    upgrade_audit = audit_benzinga_snapshot(
        _benzinga_snapshot(tmp_path / "upgrade", [_rating_row("upgrade-1")])
    )
    normalized = normalize_firm_rating_event(
        upgrade_audit, ontology, provider_event_id="upgrade-1"
    )
    assert isinstance(normalized, FirmNormalizedRatingEvent)
    assert normalized.rating_change == Fraction(1)
    assert normalized.contributes_rating_revision

    wrong_direction_audit = audit_benzinga_snapshot(
        _benzinga_snapshot(
            tmp_path / "wrong-direction",
            [_rating_row("wrong-1", action="downgrades")],
        )
    )
    wrong_direction = normalize_firm_rating_event(
        wrong_direction_audit, ontology, provider_event_id="wrong-1"
    )
    assert isinstance(wrong_direction, FirmNormalizationRefusal)
    assert wrong_direction.reason is TransitionRefusalReason.ACTION_DIRECTION_MISMATCH

    maintain_audit = audit_benzinga_snapshot(
        _benzinga_snapshot(
            tmp_path / "maintain",
            [_rating_row("maintain-1", action="maintains")],
        )
    )
    maintain = normalize_firm_rating_event(
        maintain_audit, ontology, provider_event_id="maintain-1"
    )
    assert isinstance(maintain, FirmNormalizationRefusal)
    assert maintain.reason is TransitionRefusalReason.NONCHANGE_ACTION_CHANGED_RATING

    ambiguous_audit = audit_benzinga_snapshot(
        _benzinga_snapshot(
            tmp_path / "ambiguous",
            [_rating_row("ambiguous-1", rating="Positive")],
        )
    )
    ambiguous = normalize_firm_rating_event(
        ambiguous_audit, ontology, provider_event_id="ambiguous-1"
    )
    assert isinstance(ambiguous, FirmNormalizationRefusal)
    assert ambiguous.reason is TransitionRefusalReason.UNREVIEWED_RATING_LABEL


def test_initiation_never_becomes_a_fictitious_neutral_to_buy_change(tmp_path):
    ontology = _write_ontology(tmp_path / "ontology.json", _three_level_entries())
    initiation_audit = audit_benzinga_snapshot(
        _benzinga_snapshot(
            tmp_path / "initiation",
            [
                _rating_row(
                    "initiation-1",
                    action="initiates_coverage_on",
                    previous_rating=None,
                )
            ],
        )
    )
    normalized = normalize_firm_rating_event(
        initiation_audit, ontology, provider_event_id="initiation-1"
    )
    assert isinstance(normalized, FirmNormalizedRatingEvent)
    assert normalized.current_mapping.score == Fraction(1)
    assert normalized.previous_mapping is None
    assert normalized.rating_change is None
    assert not normalized.contributes_rating_revision


def test_target_only_and_termination_do_not_enter_the_rating_change_channel(tmp_path):
    ontology = _write_ontology(tmp_path / "ontology.json", _three_level_entries())
    target = _rating_row(
        "target-1", action=None, rating=None, previous_rating=None
    )
    target["price_target_action"] = "raises"
    termination = _rating_row(
        "termination-1",
        action="terminates_coverage_on",
        rating="Unreviewed Legacy Label",
        previous_rating=None,
    )
    audit = audit_benzinga_snapshot(
        _benzinga_snapshot(tmp_path / "separate-channels", [target, termination])
    )
    result = normalize_firm_rating_audit(audit, ontology)
    assert not result.refusals
    assert len(result.events) == 2
    assert all(event.current_mapping is None for event in result.events)
    assert all(event.rating_change is None for event in result.events)


def test_firm_normalization_is_exhaustive_and_rejects_fabricated_source_event(
    tmp_path,
):
    ontology = _write_ontology(tmp_path / "ontology.json", _three_level_entries())
    audit = audit_benzinga_snapshot(
        _benzinga_snapshot(
            tmp_path / "audit",
            [_rating_row("upgrade-1"), _rating_row("ambiguous-1", rating="Positive")],
        )
    )
    result = normalize_firm_rating_audit(audit, ontology)
    assert len(result.events) == 1
    assert len(result.refusals) == 1
    assert result.source_audit_sha256 == audit.audit_sha256
    assert revalidate_firm_rating_normalization(
        result, audit=audit, ontology=ontology
    ) is result

    fabricated_record = dataclasses.replace(
        audit.records[0], current_rating="Caller Selected Rating"
    )
    fabricated_audit = dataclasses.replace(
        audit, records=(fabricated_record, audit.records[1])
    )
    with pytest.raises(RatingsIngestError, match="source-derived"):
        normalize_firm_rating_event(
            fabricated_audit, ontology, provider_event_id="upgrade-1"
        )


def _candidate(
    event_id: str,
    *,
    previous: Fraction = Fraction(0),
    current: Fraction = Fraction(1),
    institution: str = "institution-1",
    security: str = "security-1",
    day: str = "2020-01-02",
):
    return DailyRatingContributionCandidate(
        canonical_event_id=event_id,
        institution_id=institution,
        security_id=security,
        trading_day=day,
        previous_score=previous,
        current_score=current,
    )


def test_daily_dedupe_links_identical_raw_events_and_emits_one_contribution():
    result = deduplicate_daily_rating_contributions(
        (_candidate("event-2"), _candidate("event-1"))
    )
    assert not result.refusals
    assert len(result.contributions) == 1
    contribution = result.contributions[0]
    assert contribution.contributing_event_id == "event-1"
    assert contribution.linked_event_ids == ("event-1", "event-2")
    assert contribution.rating_change == Fraction(1)


def test_daily_dedupe_refuses_conflicting_economics_and_never_uses_ticker():
    result = deduplicate_daily_rating_contributions(
        (
            _candidate("event-1"),
            _candidate("event-2", previous=Fraction(1), current=Fraction(0)),
            _candidate("event-3", institution="institution-2"),
        )
    )
    assert len(result.contributions) == 1
    assert result.contributions[0].institution_id == "institution-2"
    assert len(result.refusals) == 1
    assert result.refusals[0].reason is (
        DailyDedupeRefusalReason.CONFLICTING_SAME_DAY_ECONOMIC_EVENTS
    )
    assert result.refusals[0].linked_event_ids == ("event-1", "event-2")


def test_daily_dedupe_rejects_duplicate_event_ids_and_non_exact_scores():
    with pytest.raises(RatingsIngestError, match="unique"):
        deduplicate_daily_rating_contributions(
            (_candidate("event-1"), _candidate("event-1", institution="institution-2"))
        )
    with pytest.raises(RatingsIngestError, match="Fractions"):
        DailyRatingContributionCandidate(
            canonical_event_id="event-1",
            institution_id="institution-1",
            security_id="security-1",
            trading_day="2020-01-02",
            previous_score=0,  # type: ignore[arg-type]
            current_score=Fraction(1),
        )


def test_upgrade_with_nonpositive_reviewed_change_is_direction_mismatch(tmp_path):
    """The UPGRADE branch of the direction gate needs its own regression.

    The sibling test covers only the downgrade branch, so deleting the
    upgrade-side check (an 'upgrades' action whose reviewed mapping moves the
    score down or not at all) previously left the whole file green. One case
    per branch, so neither can vanish behind the other.
    """
    ontology = _write_ontology(tmp_path / "ontology.json", _three_level_entries())

    # 'upgrades' action, but the reviewed order says Buy -> Hold is downward.
    downward_audit = audit_benzinga_snapshot(
        _benzinga_snapshot(
            tmp_path / "upgrade-downward",
            [
                _rating_row(
                    "upgrade-down-1",
                    action="upgrades",
                    rating="Hold",
                    previous_rating="Buy",
                )
            ],
        )
    )
    downward = normalize_firm_rating_event(
        downward_audit, ontology, provider_event_id="upgrade-down-1"
    )
    assert isinstance(downward, FirmNormalizationRefusal)
    assert downward.reason is TransitionRefusalReason.ACTION_DIRECTION_MISMATCH

    # 'upgrades' between two reviewed aliases of the SAME rank is a zero
    # change: raw labels differ so structural ingest accepts the row, and only
    # the reviewed order can prove the claimed upgrade moved nothing.
    alias_entries = sorted(
        _three_level_entries()
        + [_entry("Overweight", 3, 3, quality="reviewed_alias")],
        key=lambda entry: (
            entry["provider_firm_id"],
            entry["valid_from"],
            "9999-12-31" if entry["valid_to"] is None else entry["valid_to"],
            entry["ordered_rank"],
            entry["raw_label"].casefold(),
            entry["raw_label"],
        ),
    )
    alias_ontology = _write_ontology(tmp_path / "alias-ontology.json", alias_entries)
    zero_audit = audit_benzinga_snapshot(
        _benzinga_snapshot(
            tmp_path / "upgrade-zero",
            [
                _rating_row(
                    "upgrade-zero-1",
                    action="upgrades",
                    rating="Overweight",
                    previous_rating="Buy",
                )
            ],
        )
    )
    zero = normalize_firm_rating_event(
        zero_audit, alias_ontology, provider_event_id="upgrade-zero-1"
    )
    assert isinstance(zero, FirmNormalizationRefusal)
    assert zero.reason is TransitionRefusalReason.ACTION_DIRECTION_MISMATCH
