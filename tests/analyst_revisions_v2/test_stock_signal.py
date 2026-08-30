from __future__ import annotations

import dataclasses
from datetime import date, timedelta
from decimal import Decimal, localcontext
from fractions import Fraction

import pytest

import research.analyst_revisions_v2.stock_signal as stock_signal_module
from data.exchange_calendar import session_open_instant, trading_sessions
from research.analyst_revisions_v2.canonical import (
    canonical_json_bytes,
    format_utc_timestamp,
)
from research.analyst_revisions_v2.firm_ontology import (
    FIRM_ONTOLOGY_SCHEMA,
    load_reviewed_firm_rating_ontology,
)
from research.analyst_revisions_v2.formulas import (
    ActivityAwareObservation,
    ActivityObservationState,
    FormulaError,
    analyst_reliability,
    analyst_decimal_context,
    derive_verified_analyst_policy,
    rating_decay_weight,
    robust_activity_group_normalize,
    stock_reliability,
)
from research.analyst_revisions_v2.ratings_ingest import (
    BENZINGA_PROVIDER_CONTRACT_ID,
    BENZINGA_PROVIDER_CONTRACT_SHA256,
    audit_benzinga_snapshot,
    normalize_firm_rating_audit,
)
from research.analyst_revisions_v2.security_master import (
    audit_benzinga_security_identities,
    bind_firm_normalization_to_security_identities,
    load_pit_security_master,
)
from research.analyst_revisions_v2.snapshot import load_verified_snapshot
from research.analyst_revisions_v2.stock_signal import (
    CommonEventEvidence,
    DiagnosticChannel,
    InstitutionMappingEvidence,
    PROVEN_INELIGIBLE_IDENTITY_REFUSAL_REASONS,
    RESIDUALIZATION_BLOCK,
    STRUCTURAL_ONLY_AUTHORITY,
    STRUCTURAL_STOCK_EVIDENCE_SCHEMA,
    SectorClassificationEvidence,
    StockDataQualityEvidence,
    StockRawState,
    StockScoreRefusalReason,
    StockSignalError,
    StructuralStockScoreEvidence,
    build_structural_stock_diagnostics,
    build_structural_stock_score_candidate,
    revalidate_structural_stock_score_candidate,
)

from ._helpers import write_snapshot


DECISION_SESSION = "2026-08-26"
EVIDENCE_HASH = "8" * 64
SOURCE_HASH = "9" * 64


@pytest.fixture(scope="module")
def policy(tmp_path_factory: pytest.TempPathFactory):
    from research.analyst_revisions_v2.preregistration import (
        load_reviewed_preregistration,
    )
    from tests.test_analyst_revisions_v2_preregistration import _anchored_spec

    patcher = pytest.MonkeyPatch()
    path, _ = _anchored_spec(
        tmp_path_factory.mktemp("arv2-stock-policy-authority"), patcher
    )
    value = derive_verified_analyst_policy(load_reviewed_preregistration(path))
    try:
        yield value
    finally:
        patcher.undo()


def _issuer(issuer_id: str):
    return {
        "issuer_id": issuer_id,
        "cik": None,
        "incorporation_country": "US",
        "valid_from": "2010-01-01",
        "valid_to": None,
        "valid_to_available_at": None,
        "available_at": "2010-01-01T00:00:00.000000Z",
        "evidence_id": f"evidence-{issuer_id}",
        "evidence_sha256": EVIDENCE_HASH,
    }


def _security(
    security_id: str,
    issuer_id: str,
    *,
    security_type: str = "common_stock",
):
    return {
        "security_id": security_id,
        "issuer_id": issuer_id,
        "share_class_id": f"class-{security_id}",
        "security_type": security_type,
        "isin": None,
        "figi": None,
        "vendor_ids": [
            {
                "provider": "fixture",
                "value": f"vendor-{security_id}",
                "valid_from": "2010-01-01",
                "valid_to": None,
                "valid_to_available_at": None,
                "available_at": "2010-01-01T00:00:00.000000Z",
                "evidence_id": f"vendor-evidence-{security_id}",
                "evidence_sha256": EVIDENCE_HASH,
            }
        ],
        "valid_from": "2010-01-01",
        "valid_to": None,
        "valid_to_available_at": None,
        "available_at": "2010-01-01T00:00:00.000000Z",
        "evidence_id": f"evidence-{security_id}",
        "evidence_sha256": EVIDENCE_HASH,
    }


def _listing(
    index: int,
    security_id: str,
    *,
    available_at: str = "2010-01-01T00:00:00.000000Z",
    valid_to: str | None = None,
    valid_to_available_at: str | None = None,
):
    return {
        "listing_id": f"listing-{index:03d}",
        "security_id": security_id,
        "ticker": f"S{index:03d}",
        "exchange": "XNAS",
        "country": "US",
        "valid_from": "2010-01-01",
        "valid_to": valid_to,
        "valid_to_available_at": valid_to_available_at,
        "available_at": available_at,
        "evidence_id": f"listing-evidence-{index:03d}",
        "evidence_sha256": EVIDENCE_HASH,
    }


def _master(
    path,
    count: int,
    *,
    include_ineligible_adr: bool = False,
    exact_open_listing_index: int | None = None,
    exact_open_listing_closure_index: int | None = None,
):
    issuers = [_issuer(f"issuer-{index:03d}") for index in range(count)]
    securities = [
        _security(f"security-{index:03d}", f"issuer-{index:03d}")
        for index in range(count)
    ]
    listings = [
        _listing(
            index,
            f"security-{index:03d}",
            available_at=(
                format_utc_timestamp(session_open_instant(DECISION_SESSION))
                if index == exact_open_listing_index
                else "2010-01-01T00:00:00.000000Z"
            ),
            valid_to=(
                "2026-01-01"
                if index == exact_open_listing_closure_index
                else None
            ),
            valid_to_available_at=(
                format_utc_timestamp(session_open_instant(DECISION_SESSION))
                if index == exact_open_listing_closure_index
                else None
            ),
        )
        for index in range(count)
    ]
    lineage_events = []
    if exact_open_listing_closure_index is not None:
        index = exact_open_listing_closure_index
        decision_at = format_utc_timestamp(
            session_open_instant(DECISION_SESSION)
        )
        successor = _listing(
            index,
            f"security-{index:03d}",
            available_at=decision_at,
        )
        successor.update(
            {
                "listing_id": f"listing-{index:03d}-successor",
                "exchange": "OTCM",
                "valid_from": "2026-01-01",
                "evidence_id": f"listing-successor-evidence-{index:03d}",
            }
        )
        listings.append(successor)
        lineage_events.append(
            {
                "lineage_event_id": f"lineage-listing-change-{index:03d}",
                "kind": "listing_change",
                "security_id": f"security-{index:03d}",
                "effective_date": "2026-01-01",
                "available_at": decision_at,
                "successor_security_id": None,
                "evidence_id": f"lineage-evidence-{index:03d}",
                "evidence_sha256": EVIDENCE_HASH,
            }
        )
    if include_ineligible_adr:
        issuers.append(_issuer("issuer-adr"))
        securities.append(
            _security(
                "security-adr",
                "issuer-adr",
                security_type="adr",
            )
        )
        listings.append(_listing(999, "security-adr"))
    payload = {
        "schema": "arv2-pit-security-master-v1",
        "security_master_id": "security-master-stock-fixture",
        "version": "version-1",
        "created_at": "2026-08-29T00:00:00.000000Z",
        "source_id": "synthetic-stock-master-source",
        "source_sha256": SOURCE_HASH,
        "issuers": sorted(issuers, key=lambda item: item["issuer_id"]),
        "securities": sorted(
            securities, key=lambda item: item["security_id"]
        ),
        "listings": sorted(
            listings,
            key=lambda item: (
                item["ticker"],
                item["valid_from"],
                item["exchange"],
                item["security_id"],
                item["listing_id"],
            ),
        ),
        "lineage_events": lineage_events,
    }
    path.write_bytes(canonical_json_bytes(payload))
    return load_pit_security_master(path)


def _ontology(path, firms: tuple[str, ...], *, scale_size: int = 2):
    labels = (
        (("Hold", 1), ("Buy", 2))
        if scale_size == 2
        else (("Hold", 1), ("Buy", 2), ("Strong Buy", 3))
    )
    entries = []
    for firm_id in firms:
        for label, rank in labels:
            entries.append(
                {
                    "provider_firm_id": firm_id,
                    "firm_name": f"Broker {firm_id}",
                    "valid_from": "2010-01-01",
                    "valid_to": None,
                    "raw_label": label,
                    "ordered_rank": rank,
                    "scale_size": scale_size,
                    "scope": "absolute",
                    "mapping_quality": "reviewed_primary",
                    "reviewer": "Independent Reviewer",
                    "source_evidence_id": f"ontology-{firm_id}-{rank}",
                    "source_evidence_sha256": EVIDENCE_HASH,
                }
            )
    entries.sort(
        key=lambda item: (
            item["provider_firm_id"],
            item["valid_from"],
            "9999-12-31",
            item["ordered_rank"],
            item["raw_label"].casefold(),
            item["raw_label"],
        )
    )
    payload = {
        "schema": FIRM_ONTOLOGY_SCHEMA,
        "ontology_id": "ontology-stock-fixture",
        "version": "version-1",
        "status": "reviewed",
        "reviewed_at": "2026-08-29T00:00:00.000000Z",
        "entries": entries,
    }
    path.write_bytes(canonical_json_bytes(payload))
    return load_reviewed_firm_rating_ontology(path)


def _session_and_public_date(age: int) -> tuple[str, str]:
    decision = session_open_instant(DECISION_SESSION).date()
    sessions = trading_sessions(decision - timedelta(days=180), decision)
    decision_index = len(sessions) - 1
    eligible_index = decision_index - age
    return (
        sessions[eligible_index].isoformat(),
        sessions[eligible_index - 2].isoformat(),
    )


def _rating_row(
    event_id: str,
    security_index: int,
    *,
    age: int,
    firm_id: str = "firm-1",
    action: str = "upgrades",
    current: str = "Buy",
    previous: str = "Hold",
):
    _, public_date = _session_and_public_date(age)
    return {
        "event_year": int(public_date[:4]),
        "benzinga_id": event_id,
        "benzinga_firm_id": firm_id,
        "firm": f"Broker {firm_id}",
        "benzinga_analyst_id": f"analyst-{firm_id}",
        "analyst": f"Analyst {firm_id}",
        "date": public_date,
        "time": "09:31:02",
        "last_updated": f"{public_date}T12:00:00Z",
        "rating_action": action,
        "rating": current,
        "previous_rating": previous,
        "ticker": f"S{security_index:03d}",
    }


def _chain(
    tmp_path,
    *,
    security_count: int = 20,
    rows: list[dict] | None = None,
    firms: tuple[str, ...] = ("firm-1",),
    scale_size: int = 2,
    captured_at: str | None = None,
    include_ineligible_adr: bool = False,
    exact_open_listing_index: int | None = None,
    exact_open_listing_closure_index: int | None = None,
    history_first_year: int = 2013,
):
    tmp_path.mkdir(parents=True, exist_ok=True)
    master = _master(
        tmp_path / "master.json",
        security_count,
        include_ineligible_adr=include_ineligible_adr,
        exact_open_listing_index=exact_open_listing_index,
        exact_open_listing_closure_index=exact_open_listing_closure_index,
    )
    ontology = _ontology(tmp_path / "ontology.json", firms, scale_size=scale_size)
    if rows is None:
        rows = [
            _rating_row(f"event-{index:03d}", index, age=index)
            for index in range(security_count)
        ]
    rows_by_year: dict[int, list[dict]] = {
        year: [] for year in range(history_first_year, 2027)
    }
    for row in rows:
        rows_by_year.setdefault(row["event_year"], []).append(row)
    decision_at = format_utc_timestamp(session_open_instant(DECISION_SESSION))
    write_snapshot(
        tmp_path / "snapshot",
        rows_by_year=rows_by_year,
        requested_first_year=history_first_year,
        requested_last_year=2026,
        snapshot_id="snapshot-stock-fixture",
        provider_contract_id=BENZINGA_PROVIDER_CONTRACT_ID,
        provider_contract_sha256=BENZINGA_PROVIDER_CONTRACT_SHA256,
        captured_at=decision_at if captured_at is None else captured_at,
    )
    snapshot = load_verified_snapshot(
        tmp_path / "snapshot", verified_at="2026-08-29T12:00:00.000000Z"
    )
    ingest = audit_benzinga_snapshot(snapshot)
    firm_result = normalize_firm_rating_audit(ingest, ontology)
    identity_audit = audit_benzinga_security_identities(ingest, master)
    upstream = bind_firm_normalization_to_security_identities(
        firm_result,
        identity_audit,
        ingest_audit=ingest,
        ontology=ontology,
        master=master,
    )
    institution_mappings = tuple(
        InstitutionMappingEvidence(
            firm_id,
            f"institution-{firm_id}",
            "2010-01-01",
            None,
            None,
            "2010-01-01T00:00:00.000000Z",
            EVIDENCE_HASH,
        )
        for firm_id in sorted(firms)
    )
    common_events = tuple(
        CommonEventEvidence(
            row["benzinga_id"],
            f"catalyst-{row['benzinga_id']}",
            f"{row['date']}T12:00:00.000000Z",
            EVIDENCE_HASH,
        )
        for row in sorted(rows, key=lambda value: value["benzinga_id"])
    )
    classifications = tuple(
        SectorClassificationEvidence(
            f"security-{index:03d}",
            "sector-1",
            "2010-01-01",
            None,
            None,
            "2010-01-01T00:00:00.000000Z",
            EVIDENCE_HASH,
        )
        for index in range(security_count)
    )
    quality = tuple(
        StockDataQualityEvidence(
            f"security-{index:03d}",
            DECISION_SESSION,
            "2026-08-25T20:00:00.000000Z",
            Decimal("1"),
            "fixture-measured-quality-v1",
            EVIDENCE_HASH,
        )
        for index in range(security_count)
    )
    evidence = StructuralStockScoreEvidence(
        STRUCTURAL_STOCK_EVIDENCE_SCHEMA,
        ingest.audit_sha256,
        master.security_master_id,
        master.payload_sha256,
        "fixture-institution-source",
        "fixture-catalyst-source",
        "fixture-classification-source",
        "fixture-quality-source",
        institution_mappings,
        common_events,
        classifications,
        quality,
    )
    arguments = {
        "upstream": upstream,
        "evidence": evidence,
        "decision_session": DECISION_SESSION,
        "firm_result": firm_result,
        "identity_audit": identity_audit,
        "ingest_audit": ingest,
        "ontology": ontology,
        "master": master,
    }
    return arguments


def _build(arguments, policy):
    return build_structural_stock_score_candidate(policy=policy, **arguments)


def _diagnostics(candidate, arguments, policy):
    return build_structural_stock_diagnostics(
        candidate,
        arguments["upstream"],
        arguments["evidence"],
        policy=policy,
        firm_result=arguments["firm_result"],
        identity_audit=arguments["identity_audit"],
        ingest_audit=arguments["ingest_audit"],
        ontology=arguments["ontology"],
        master=arguments["master"],
    )


def test_decay_and_stock_reliability_goldens_are_distinct_from_etf_formula(policy):
    assert rating_decay_weight(0, policy=policy) == Decimal("1")
    assert rating_decay_weight(20, policy=policy) == Decimal("0.5")
    assert rating_decay_weight(40, policy=policy) == Decimal("0.25")
    assert rating_decay_weight(1, policy=policy) == Decimal(
        "0.96593632892484555106514431292046389939073731287925"
    )
    assert stock_reliability(independent_effective_n=3, quality="0.8") == Decimal(
        "0.4"
    )
    assert analyst_reliability(
        coverage=1, independent_effective_n=3, quality="0.8"
    ) != Decimal("0.4")


@pytest.mark.parametrize("bad_age", [-1, True, Decimal("1"), "1"])
def test_decay_rejects_caller_selected_non_session_age(policy, bad_age):
    with pytest.raises(FormulaError, match="age_sessions"):
        rating_decay_weight(bad_age, policy=policy)


def test_decay_is_ambient_context_invariant(policy):
    expected = rating_decay_weight(7, policy=policy)
    with localcontext() as context:
        context.prec = 6
        assert rating_decay_weight(7, policy=policy) == expected


def test_activity_aware_zero_is_active_not_structural(policy):
    observations = tuple(
        ActivityAwareObservation(
            f"security-{index:03d}",
            (
                ActivityObservationState.ACTIVE
                if index < 5
                else ActivityObservationState.STRUCTURAL_ZERO
            ),
            Decimal(index) if index < 5 else 0,
        )
        for index in range(20)
    )
    normalized = robust_activity_group_normalize(observations, policy=policy)
    assert normalized.active_names == 5
    assert normalized.total_names == 20
    assert observations[0].state is ActivityObservationState.ACTIVE
    assert observations[0].value == 0


def test_unclipped_sector_z_uses_pdf_mad_scale(policy):
    observations = tuple(
        ActivityAwareObservation(
            f"security-{index:03d}",
            ActivityObservationState.ACTIVE,
            Decimal(index),
        )
        for index in range(20)
    )
    normalized = robust_activity_group_normalize(observations, policy=policy)
    assert normalized.available
    assert normalized.median == Decimal("9.5")
    assert normalized.mad == Decimal("5")
    with analyst_decimal_context():
        expected = Decimal("0.5") / (Decimal("1.4826") * Decimal("5"))
    assert normalized.standardized["security-010"] == expected


def test_activity_aware_normalization_refuses_duplicates_and_invalids(policy):
    observations = tuple(
        ActivityAwareObservation(
            f"security-{index:03d}",
            ActivityObservationState.ACTIVE,
            Decimal(index),
        )
        for index in range(20)
    )
    duplicate = (
        observations[0],
        dataclasses.replace(observations[1], security_id="security-000"),
        *observations[2:],
    )
    with pytest.raises(FormulaError, match="duplicate security_id"):
        robust_activity_group_normalize(duplicate, policy=policy)
    invalid = (
        dataclasses.replace(
            observations[0],
            state=ActivityObservationState.INVALID,
            value=None,
        ),
        *observations[1:],
    )
    with pytest.raises(FormulaError, match="invalid observations refuse"):
        robust_activity_group_normalize(invalid, policy=policy)


def test_full_structural_candidate_revalidates_and_pins_pdf_equation(tmp_path, policy):
    arguments = _chain(tmp_path)
    candidate = _build(arguments, policy)
    assert candidate.authority == STRUCTURAL_ONLY_AUTHORITY
    assert candidate.pdf_formula_available
    assert not candidate.final_executable_available
    assert candidate.residualization_state == RESIDUALIZATION_BLOCK
    assert len(candidate.scores) == 20
    contribution = candidate.contributions[0]
    assert contribution.age_sessions == 0
    assert contribution.rating_change == Fraction(2, 1)
    assert contribution.decay_weight == Decimal("1")
    assert contribution.decayed_value == Decimal("2")
    row = candidate.scores[0]
    assert row.raw_score == Decimal("2")
    assert row.reliability == Decimal("0.25")
    with analyst_decimal_context():
        assert row.pdf_reliable_score == row.sector_z * row.reliability
    revalidation_arguments = dict(arguments)
    revalidation_arguments.pop("decision_session")
    assert revalidate_structural_stock_score_candidate(
        candidate,
        policy=policy,
        **revalidation_arguments,
    ) is candidate
    forged = dataclasses.replace(candidate, scores=())
    with pytest.raises(StockSignalError, match="not source-derived"):
        revalidate_structural_stock_score_candidate(
            forged,
            policy=policy,
            **revalidation_arguments,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_audit_sha256", "7" * 64),
        ("security_master_id", "wrong-security-master"),
        ("security_master_sha256", "6" * 64),
    ],
)
def test_structural_evidence_must_bind_to_revalidated_upstream(
    tmp_path, policy, field, value
):
    arguments = _chain(tmp_path)
    arguments["evidence"] = dataclasses.replace(
        arguments["evidence"],
        **{field: value},
    )
    candidate = _build(arguments, policy)
    assert not candidate.scores
    assert StockScoreRefusalReason.EVIDENCE_BINDING_MISMATCH in {
        item.reason for item in candidate.refusals
    }


def test_high_level_age_uses_nyse_sessions_not_calendar_days(tmp_path, policy):
    eligible_session, public_date = _session_and_public_date(3)
    row = _rating_row("event-weekend", 0, age=3)
    arguments = _chain(
        tmp_path,
        rows=[row]
        + [
            _rating_row(f"event-{index:03d}", index, age=index + 1)
            for index in range(1, 20)
        ],
    )
    candidate = _build(arguments, policy)
    event = next(
        item
        for item in candidate.contributions
        if item.provider_event_id == "event-weekend"
    )
    assert event.eligible_session == eligible_session
    assert event.age_sessions == 3
    assert (
        date.fromisoformat(DECISION_SESSION) - date.fromisoformat(eligible_session)
    ).days == 5
    assert event.decay_weight == rating_decay_weight(3, policy=policy)
    assert public_date < eligible_session


def test_candidate_builds_one_shared_session_age_index(
    tmp_path, policy, monkeypatch
):
    arguments = _chain(tmp_path)
    original = stock_signal_module.trading_sessions
    calls = []

    def counted_sessions(first, last):
        calls.append((first, last))
        return original(first, last)

    monkeypatch.setattr(stock_signal_module, "trading_sessions", counted_sessions)
    candidate = _build(arguments, policy)
    assert candidate.pdf_formula_available
    assert len(calls) == 1


@pytest.mark.parametrize("path", ["all-delayed", "global-refusal"])
def test_candidate_skips_session_index_when_no_event_can_be_admitted(
    tmp_path, policy, monkeypatch, path
):
    if path == "all-delayed":
        rows = [
            _rating_row(f"event-{index:03d}", index, age=index)
            for index in range(20)
        ]
        for row in rows:
            row["last_updated"] = format_utc_timestamp(
                session_open_instant(DECISION_SESSION)
            )
        arguments = _chain(tmp_path, rows=rows)
        expected = StockScoreRefusalReason.INSUFFICIENT_ACTIVE_NAMES
    else:
        arguments = _chain(tmp_path)
        arguments["evidence"] = dataclasses.replace(
            arguments["evidence"],
            source_audit_sha256="7" * 64,
        )
        expected = StockScoreRefusalReason.EVIDENCE_BINDING_MISMATCH

    def unexpected_sessions(*_args, **_kwargs):
        raise AssertionError("session index must not be built")

    monkeypatch.setattr(
        stock_signal_module,
        "trading_sessions",
        unexpected_sessions,
    )
    candidate = _build(arguments, policy)
    assert not candidate.contributions
    assert not candidate.scores
    assert expected in {item.reason for item in candidate.refusals}


def test_exponential_decay_has_no_hidden_hard_lookback_cutoff(tmp_path, policy):
    rows = [
        _rating_row("event-long-history", 0, age=120),
        *[
            _rating_row(f"event-{index:03d}", index, age=index)
            for index in range(1, 20)
        ],
    ]
    candidate = _build(_chain(tmp_path, rows=rows), policy)
    contribution = next(
        item
        for item in candidate.contributions
        if item.provider_event_id == "event-long-history"
    )
    assert contribution.age_sessions == 120
    assert contribution.decay_weight == rating_decay_weight(120, policy=policy)
    assert contribution.decayed_value > 0
    score = next(
        item for item in candidate.scores if item.security_id == "security-000"
    )
    assert score.raw_state is StockRawState.ACTIVE
    assert score.raw_score > 0


def test_structural_zero_and_active_cancellation_remain_distinct(tmp_path, policy):
    rows = [
        _rating_row(f"event-{index:03d}", index, age=index)
        for index in range(19)
    ]
    arguments = _chain(tmp_path / "structural", rows=rows)
    structural = _build(arguments, policy)
    zero_row = next(
        row for row in structural.scores if row.security_id == "security-019"
    )
    assert zero_row.raw_state is StockRawState.STRUCTURAL_ZERO
    assert zero_row.raw_score == 0
    assert zero_row.independent_effective_n == 0
    assert zero_row.reliability == 0
    assert zero_row.pdf_reliable_score == 0

    cancellation_rows = [
        _rating_row(f"event-{index:03d}", index, age=index)
        for index in range(20)
    ]
    cancellation_rows[0] = _rating_row(
        "event-up", 0, age=0, firm_id="firm-1"
    )
    cancellation_rows.append(
        _rating_row(
            "event-down",
            0,
            age=0,
            firm_id="firm-2",
            action="downgrades",
            current="Hold",
            previous="Buy",
        )
    )
    cancellation_arguments = _chain(
        tmp_path / "cancellation",
        rows=cancellation_rows,
        firms=("firm-1", "firm-2"),
    )
    canceled = _build(cancellation_arguments, policy)
    canceled_row = next(
        row for row in canceled.scores if row.security_id == "security-000"
    )
    assert canceled_row.raw_state is StockRawState.ACTIVE
    assert canceled_row.raw_score == 0
    assert canceled.sector_normalizations[0].active_names == 20


def test_absolute_mass_breadth_survives_directional_cancellation(
    tmp_path, policy
):
    rows = [
        _rating_row(
            "event-old-upgrade",
            0,
            age=20,
            current="Strong Buy",
            previous="Hold",
        ),
        _rating_row(
            "event-current-downgrade",
            0,
            age=0,
            action="downgrades",
            current="Hold",
            previous="Buy",
        ),
        *[
            _rating_row(f"event-{index:03d}", index, age=index)
            for index in range(1, 20)
        ],
    ]
    arguments = _chain(tmp_path, rows=rows, scale_size=3)
    evidence = arguments["evidence"]
    arguments["evidence"] = dataclasses.replace(
        evidence,
        common_events=tuple(
            dataclasses.replace(item, common_event_id="shared-catalyst")
            if item.provider_event_id
            in {"event-old-upgrade", "event-current-downgrade"}
            else item
            for item in evidence.common_events
        ),
    )
    candidate = _build(arguments, policy)
    by_event = {
        item.provider_event_id: item
        for item in candidate.contributions
        if item.security_id == "security-000"
    }
    assert by_event["event-old-upgrade"].rating_change == Fraction(2, 1)
    assert by_event["event-old-upgrade"].decay_weight == Decimal("0.5")
    assert by_event["event-old-upgrade"].decayed_value == Decimal("1.0")
    assert by_event["event-current-downgrade"].rating_change == Fraction(-1, 1)
    assert by_event["event-current-downgrade"].decayed_value == Decimal("-1")
    canceled = next(
        row for row in candidate.scores if row.security_id == "security-000"
    )
    assert canceled.raw_state is StockRawState.ACTIVE
    assert canceled.raw_score == Decimal("0")
    assert canceled.institution_effective_n == Decimal("1")
    assert canceled.catalyst_effective_n == Decimal("1")
    assert canceled.independent_effective_n == Decimal("1")
    assert canceled.reliability == Decimal("0.25")


@pytest.mark.parametrize(
    ("security_count", "event_count", "reason"),
    [
        (19, 19, StockScoreRefusalReason.INSUFFICIENT_TOTAL_NAMES),
        (20, 4, StockScoreRefusalReason.INSUFFICIENT_ACTIVE_NAMES),
    ],
)
def test_sparse_sector_refuses_without_partial_scores(
    tmp_path, policy, security_count, event_count, reason
):
    rows = [
        _rating_row(f"event-{index:03d}", index, age=index)
        for index in range(event_count)
    ]
    candidate = _build(
        _chain(tmp_path, security_count=security_count, rows=rows), policy
    )
    assert not candidate.scores
    assert not candidate.sector_normalizations
    assert reason in {item.reason for item in candidate.refusals}


def test_two_sparse_sectors_refuse_without_market_level_fallback(tmp_path, policy):
    arguments = _chain(tmp_path, security_count=30)
    evidence = arguments["evidence"]
    arguments["evidence"] = dataclasses.replace(
        evidence,
        sector_classifications=tuple(
            dataclasses.replace(
                item,
                sector_id="sector-1" if index < 15 else "sector-2",
            )
            for index, item in enumerate(evidence.sector_classifications)
        ),
    )
    candidate = _build(arguments, policy)
    assert not candidate.scores
    assert not candidate.sector_normalizations
    sparse = {
        item.scope_id
        for item in candidate.refusals
        if item.reason is StockScoreRefusalReason.INSUFFICIENT_TOTAL_NAMES
    }
    assert sparse == {"sector-1", "sector-2"}


def test_zero_mad_refuses_without_epsilon_or_market_fallback(tmp_path, policy):
    rows = [
        _rating_row(f"event-{index:03d}", index, age=0) for index in range(20)
    ]
    candidate = _build(_chain(tmp_path, rows=rows), policy)
    assert not candidate.scores
    assert {item.reason for item in candidate.refusals} == {
        StockScoreRefusalReason.ZERO_MAD
    }


def test_fixed_clip_and_catalyst_independence_are_applied_after_raw_sum(
    tmp_path, policy
):
    firms = tuple(f"firm-{index}" for index in range(10))
    rows = [
        _rating_row(
            f"event-outlier-{index}",
            0,
            age=index,
            firm_id=f"firm-{index}",
        )
        for index in range(10)
    ] + [
        _rating_row(
            f"event-peer-{index:03d}",
            index,
            age=index + 19,
            firm_id="firm-0",
        )
        for index in range(1, 20)
    ]
    arguments = _chain(tmp_path, rows=rows, firms=firms)
    evidence = arguments["evidence"]
    shared_catalysts = tuple(
        dataclasses.replace(item, common_event_id="one-common-catalyst")
        if item.provider_event_id.startswith("event-outlier-")
        else item
        for item in evidence.common_events
    )
    arguments["evidence"] = dataclasses.replace(
        evidence, common_events=shared_catalysts
    )
    candidate = _build(arguments, policy)
    outlier = next(row for row in candidate.scores if row.security_id == "security-000")
    assert outlier.sector_z == Decimal("4")
    assert outlier.catalyst_effective_n == Decimal("1")
    assert outlier.institution_effective_n > Decimal("1")
    assert outlier.independent_effective_n == Decimal("1")


def test_fixed_clip_is_symmetric_for_negative_outlier(tmp_path, policy):
    firms = tuple(f"firm-{index}" for index in range(10))
    rows = [
        _rating_row(
            f"event-outlier-{index}",
            0,
            age=index,
            firm_id=f"firm-{index}",
            action="downgrades",
            current="Hold",
            previous="Buy",
        )
        for index in range(10)
    ] + [
        _rating_row(
            f"event-peer-{index:03d}",
            index,
            age=index + 19,
            firm_id="firm-0",
        )
        for index in range(1, 20)
    ]
    candidate = _build(_chain(tmp_path, rows=rows, firms=firms), policy)
    outlier = next(
        row for row in candidate.scores if row.security_id == "security-000"
    )
    assert outlier.sector_z == Decimal("-4")


def test_quality_shrinks_after_normalization_and_never_changes_sector_z(
    tmp_path, policy
):
    arguments = _chain(tmp_path)
    baseline = _build(arguments, policy)
    evidence = arguments["evidence"]
    lower_quality = (
        dataclasses.replace(evidence.data_quality[0], q_data=Decimal("0.8")),
        *evidence.data_quality[1:],
    )
    arguments["evidence"] = dataclasses.replace(
        evidence, data_quality=lower_quality
    )
    changed = _build(arguments, policy)
    baseline_rows = {row.security_id: row for row in baseline.scores}
    changed_rows = {row.security_id: row for row in changed.scores}
    assert {
        security_id: (row.raw_score, row.sector_z)
        for security_id, row in baseline_rows.items()
    } == {
        security_id: (row.raw_score, row.sector_z)
        for security_id, row in changed_rows.items()
    }
    assert changed_rows["security-000"].reliability == Decimal("0.2")
    assert (
        changed_rows["security-000"].pdf_reliable_score
        != baseline_rows["security-000"].pdf_reliable_score
    )


def test_master_cutoff_matches_reviewed_arv2_2_inclusive_pit_semantics(
    tmp_path, policy
):
    rows = [
        _rating_row(f"event-{index:03d}", index, age=index)
        for index in range(20)
    ]
    newly_known_arguments = _chain(
        tmp_path / "newly-known",
        security_count=21,
        rows=rows,
        exact_open_listing_index=20,
    )
    newly_known = _build(newly_known_arguments, policy)
    assert newly_known.pdf_formula_available
    assert "security-020" in newly_known.universe_security_ids
    new_row = next(
        item for item in newly_known.scores if item.security_id == "security-020"
    )
    assert new_row.raw_state is StockRawState.STRUCTURAL_ZERO

    closed_arguments = _chain(
        tmp_path / "closed",
        security_count=21,
        rows=rows,
        exact_open_listing_closure_index=20,
    )
    closed = _build(closed_arguments, policy)
    assert closed.pdf_formula_available
    assert "security-020" not in closed.universe_security_ids
    assert len(closed.scores) == 20


def test_future_classification_closure_is_not_visible_at_decision(tmp_path, policy):
    arguments = _chain(tmp_path)
    evidence = arguments["evidence"]
    first = dataclasses.replace(
        evidence.sector_classifications[0],
        valid_to="2026-01-01",
        valid_to_available_at=format_utc_timestamp(
            session_open_instant(DECISION_SESSION)
        ),
    )
    arguments["evidence"] = dataclasses.replace(
        evidence,
        sector_classifications=(first, *evidence.sector_classifications[1:]),
    )
    candidate = _build(arguments, policy)
    assert candidate.pdf_formula_available
    assert next(
        row for row in candidate.scores if row.security_id == "security-000"
    ).sector_id == "sector-1"


def test_future_institution_closure_is_not_visible_at_decision(tmp_path, policy):
    arguments = _chain(tmp_path)
    evidence = arguments["evidence"]
    mapping = dataclasses.replace(
        evidence.institution_mappings[0],
        valid_to="2026-01-01",
        valid_to_available_at=format_utc_timestamp(
            session_open_instant(DECISION_SESSION)
        ),
    )
    arguments["evidence"] = dataclasses.replace(
        evidence,
        institution_mappings=(mapping,),
    )
    candidate = _build(arguments, policy)
    assert candidate.pdf_formula_available
    assert {
        item.institution_id for item in candidate.contributions
    } == {"institution-firm-1"}


@pytest.mark.parametrize(
    ("field", "reason"),
    [
        (
            "sector_classifications",
            StockScoreRefusalReason.MISSING_SECTOR_CLASSIFICATION,
        ),
        (
            "institution_mappings",
            StockScoreRefusalReason.MISSING_INSTITUTION_MAPPING,
        ),
    ],
)
def test_closure_known_before_decision_is_enforced(
    tmp_path, policy, field, reason
):
    arguments = _chain(tmp_path)
    evidence = arguments["evidence"]
    values = list(getattr(evidence, field))
    values[0] = dataclasses.replace(
        values[0],
        valid_to="2026-01-01",
        valid_to_available_at="2026-01-02T00:00:00.000000Z",
    )
    arguments["evidence"] = dataclasses.replace(
        evidence,
        **{field: tuple(values)},
    )
    candidate = _build(arguments, policy)
    assert not candidate.scores
    assert reason in {item.reason for item in candidate.refusals}


def test_hidden_classification_closure_yields_named_as_known_ambiguity(
    tmp_path, policy
):
    arguments = _chain(tmp_path)
    evidence = arguments["evidence"]
    old = dataclasses.replace(
        evidence.sector_classifications[0],
        valid_to="2020-01-01",
        valid_to_available_at="2026-08-27T13:30:00.000000Z",
    )
    successor = SectorClassificationEvidence(
        "security-000",
        "sector-2",
        "2020-01-01",
        None,
        None,
        "2020-01-01T00:00:00.000000Z",
        "7" * 64,
    )
    arguments["evidence"] = dataclasses.replace(
        evidence,
        sector_classifications=(
            old,
            successor,
            *evidence.sector_classifications[1:],
        ),
    )
    candidate = _build(arguments, policy)
    assert not candidate.scores
    assert StockScoreRefusalReason.AMBIGUOUS_SECTOR_CLASSIFICATION in {
        item.reason for item in candidate.refusals
    }


def test_hidden_institution_closure_yields_named_as_known_ambiguity(
    tmp_path, policy
):
    arguments = _chain(tmp_path)
    evidence = arguments["evidence"]
    old = dataclasses.replace(
        evidence.institution_mappings[0],
        valid_to="2020-01-01",
        valid_to_available_at="2026-08-27T13:30:00.000000Z",
    )
    successor = InstitutionMappingEvidence(
        "firm-1",
        "institution-successor",
        "2020-01-01",
        None,
        None,
        "2020-01-01T00:00:00.000000Z",
        "7" * 64,
    )
    arguments["evidence"] = dataclasses.replace(
        evidence,
        institution_mappings=(old, successor),
    )
    candidate = _build(arguments, policy)
    assert not candidate.scores
    assert StockScoreRefusalReason.AMBIGUOUS_INSTITUTION_MAPPING in {
        item.reason for item in candidate.refusals
    }


@pytest.mark.parametrize(
    ("field", "late", "reason"),
    [
        (
            "sector_classifications",
            False,
            StockScoreRefusalReason.MISSING_SECTOR_CLASSIFICATION,
        ),
        (
            "sector_classifications",
            True,
            StockScoreRefusalReason.LATE_SECTOR_CLASSIFICATION,
        ),
        ("data_quality", False, StockScoreRefusalReason.MISSING_DATA_QUALITY),
        ("data_quality", True, StockScoreRefusalReason.LATE_DATA_QUALITY),
        (
            "institution_mappings",
            False,
            StockScoreRefusalReason.MISSING_INSTITUTION_MAPPING,
        ),
        (
            "institution_mappings",
            True,
            StockScoreRefusalReason.LATE_INSTITUTION_MAPPING,
        ),
        ("common_events", False, StockScoreRefusalReason.MISSING_COMMON_EVENT_EVIDENCE),
        ("common_events", True, StockScoreRefusalReason.LATE_COMMON_EVENT_EVIDENCE),
    ],
)
def test_missing_or_late_structural_evidence_fails_closed(
    tmp_path, policy, field, late, reason
):
    arguments = _chain(tmp_path)
    evidence = arguments["evidence"]
    values = list(getattr(evidence, field))
    if late:
        values[0] = dataclasses.replace(
            values[0],
            available_at=format_utc_timestamp(
                session_open_instant(DECISION_SESSION)
            ),
        )
    else:
        values.pop(0)
    arguments["evidence"] = dataclasses.replace(evidence, **{field: tuple(values)})
    candidate = _build(arguments, policy)
    assert not candidate.scores
    assert reason in {item.reason for item in candidate.refusals}
    if late:
        matching = [item for item in candidate.refusals if item.reason is reason]
        assert EVIDENCE_HASH in {
            evidence_id
            for item in matching
            for evidence_id in item.evidence_ids
        }


def test_dedupe_conflict_and_common_catalyst_conflict_are_not_dropped(tmp_path, policy):
    conflict_rows = [
        _rating_row("event-a", 0, age=0, current="Buy", previous="Hold"),
        _rating_row("event-b", 0, age=0, current="Strong Buy", previous="Hold"),
    ] + [
        _rating_row(f"event-{index:03d}", index, age=index)
        for index in range(1, 20)
    ]
    conflict = _build(
        _chain(tmp_path / "economic", rows=conflict_rows, scale_size=3), policy
    )
    assert StockScoreRefusalReason.DAILY_DEDUPE_CONFLICT in {
        item.reason for item in conflict.refusals
    }

    duplicate_rows = [
        _rating_row("event-c", 0, age=0),
        _rating_row("event-d", 0, age=0),
    ] + [
        _rating_row(f"event-z-{index:03d}", index, age=index)
        for index in range(1, 20)
    ]
    duplicate = _build(_chain(tmp_path / "catalyst", rows=duplicate_rows), policy)
    assert StockScoreRefusalReason.CONFLICTING_COMMON_EVENT_EVIDENCE in {
        item.reason for item in duplicate.refusals
    }


def test_identical_daily_updates_are_linked_and_counted_once(tmp_path, policy):
    rows = [
        _rating_row("duplicate-a", 0, age=0),
        _rating_row("duplicate-b", 0, age=0),
        *[
            _rating_row(f"event-{index:03d}", index, age=index)
            for index in range(1, 20)
        ],
    ]
    arguments = _chain(tmp_path, rows=rows)
    evidence = arguments["evidence"]
    arguments["evidence"] = dataclasses.replace(
        evidence,
        common_events=tuple(
            dataclasses.replace(item, common_event_id="duplicate-catalyst")
            if item.provider_event_id in {"duplicate-a", "duplicate-b"}
            else item
            for item in evidence.common_events
        ),
    )
    candidate = _build(arguments, policy)
    contributions = [
        item
        for item in candidate.contributions
        if item.security_id == "security-000"
    ]
    assert len(contributions) == 1
    assert len(contributions[0].linked_event_ids) == 2
    assert contributions[0].canonical_event_id in contributions[0].linked_event_ids
    assert contributions[0].decayed_value == Decimal("2")
    score = next(
        item for item in candidate.scores if item.security_id == "security-000"
    )
    assert score.raw_score == Decimal("2")


def test_proven_ineligible_identity_refusal_does_not_poison_universe(
    tmp_path, policy
):
    assert PROVEN_INELIGIBLE_IDENTITY_REFUSAL_REASONS == frozenset(
        {
            "ineligible_issuer_country",
            "ineligible_listing_country",
            "ineligible_exchange",
            "ineligible_security_type",
        }
    )
    eligible_rows = [
        _rating_row(f"event-{index:03d}", index, age=index)
        for index in range(20)
    ]
    baseline = _build(
        _chain(tmp_path / "baseline", rows=eligible_rows),
        policy,
    )
    adr_row = _rating_row("event-adr", 999, age=0)
    arguments = _chain(
        tmp_path / "with-adr",
        rows=[*eligible_rows, adr_row],
        include_ineligible_adr=True,
    )
    assert any(
        item.reason == "ineligible_security_type"
        for item in arguments["upstream"].refusals
    )
    candidate = _build(arguments, policy)
    assert candidate.pdf_formula_available
    assert not candidate.refusals
    assert [item.to_record() for item in candidate.scores] == [
        item.to_record() for item in baseline.scores
    ]
    assert all(
        item.provider_event_id != "event-adr"
        for item in candidate.contributions
    )


def test_ontology_or_ambiguous_identity_refusal_still_blocks_cross_section(
    tmp_path, policy
):
    rows = [
        _rating_row("event-unknown-firm", 0, age=0, firm_id="firm-unknown"),
        *[
            _rating_row(f"event-{index:03d}", index, age=index)
            for index in range(1, 20)
        ],
    ]
    arguments = _chain(tmp_path, rows=rows, firms=("firm-1",))
    assert arguments["upstream"].refusals
    candidate = _build(arguments, policy)
    assert not candidate.scores
    assert StockScoreRefusalReason.UPSTREAM_IDENTITY_OR_ONTOLOGY_REFUSAL in {
        item.reason for item in candidate.refusals
    }


def test_not_yet_eligible_event_is_sliced_before_feature_construction(tmp_path, policy):
    baseline_rows = [
        _rating_row(f"event-{index:03d}", index, age=index)
        for index in range(20)
    ]
    baseline = _build(_chain(tmp_path / "baseline", rows=baseline_rows), policy)
    future = _rating_row("event-future", 0, age=0)
    future["date"] = "2026-08-25"
    future["last_updated"] = "2026-08-25T12:00:00Z"
    future["event_year"] = 2026
    appended = _build(
        _chain(tmp_path / "appended", rows=[*baseline_rows, future]), policy
    )
    assert [row.to_record() for row in appended.scores] == [
        row.to_record() for row in baseline.scores
    ]
    assert all(
        item.provider_event_id != "event-future"
        for item in appended.contributions
    )


@pytest.mark.parametrize(
    "captured_at",
    [
        "2026-08-26T13:29:00.000000Z",
        "2026-08-26T13:31:00.000000Z",
    ],
)
def test_nondecision_snapshot_is_a_named_global_refusal(
    tmp_path, policy, captured_at
):
    arguments = _chain(
        tmp_path, captured_at=captured_at
    )
    candidate = _build(arguments, policy)
    assert StockScoreRefusalReason.SOURCE_SNAPSHOT_NOT_DECISION_VINTAGE in {
        item.reason for item in candidate.refusals
    }


def test_incomplete_requested_history_is_a_named_global_refusal(
    tmp_path, policy
):
    candidate = _build(
        _chain(tmp_path, history_first_year=2014),
        policy,
    )
    assert not candidate.scores
    assert StockScoreRefusalReason.SOURCE_HISTORY_RANGE_INCOMPLETE in {
        item.reason for item in candidate.refusals
    }


def test_source_row_updated_at_decision_open_is_delayed_not_globally_refused(
    tmp_path, policy
):
    rows = [
        _rating_row(f"event-{index:03d}", index, age=index)
        for index in range(20)
    ]
    rows[0]["last_updated"] = format_utc_timestamp(
        session_open_instant(DECISION_SESSION)
    )
    candidate = _build(_chain(tmp_path, rows=rows), policy)
    assert candidate.pdf_formula_available
    assert not candidate.refusals
    assert all(
        item.provider_event_id != "event-000"
        for item in candidate.contributions
    )
    delayed = next(
        item for item in candidate.scores if item.security_id == "security-000"
    )
    assert delayed.raw_state is StockRawState.STRUCTURAL_ZERO


def test_source_row_updated_after_snapshot_capture_is_globally_refused(
    tmp_path, policy
):
    rows = [
        _rating_row(f"event-{index:03d}", index, age=index)
        for index in range(20)
    ]
    rows[0]["last_updated"] = "2026-08-26T13:31:00Z"
    candidate = _build(_chain(tmp_path, rows=rows), policy)
    assert not candidate.scores
    assert StockScoreRefusalReason.SOURCE_ROW_AFTER_CAPTURE in {
        item.reason for item in candidate.refusals
    }


def test_diagnostics_are_separate_and_cannot_change_canonical_hash(tmp_path, policy):
    arguments = _chain(tmp_path)
    candidate = _build(arguments, policy)
    canonical_hash = candidate.candidate_sha256
    diagnostics = _diagnostics(candidate, arguments, policy)
    assert diagnostics.canonical_candidate_sha256 == canonical_hash
    assert {item.channel for item in diagnostics.unavailable} == set(DiagnosticChannel)
    analyst_identity = next(
        item
        for item in diagnostics.unavailable
        if item.channel is DiagnosticChannel.UNIQUE_ANALYSTS
    )
    assert (
        analyst_identity.reason
        == "requires_authenticated_permanent_analyst_identity"
    )
    mutated = dataclasses.replace(
        diagnostics,
        rows=(
            dataclasses.replace(
                diagnostics.rows[0], directional_breadth=Decimal("-1")
            ),
            *diagnostics.rows[1:],
        ),
    )
    assert mutated.diagnostics_sha256 != diagnostics.diagnostics_sha256
    assert candidate.candidate_sha256 == canonical_hash
    with pytest.raises(StockSignalError, match="unique security IDs"):
        dataclasses.replace(
            diagnostics,
            rows=(diagnostics.rows[0], *diagnostics.rows),
        )
    with pytest.raises(StockSignalError, match="each deferred channel once"):
        dataclasses.replace(
            diagnostics,
            unavailable=diagnostics.unavailable[:-1],
        )
    forged = dataclasses.replace(candidate, contributions=())
    with pytest.raises(StockSignalError, match="not source-derived"):
        _diagnostics(forged, arguments, policy)


def test_diagnostics_hash_is_ambient_decimal_context_independent(tmp_path, policy):
    rows = [
        _rating_row("diagnostic-up-a", 0, age=0),
        _rating_row("diagnostic-up-b", 0, age=1),
        _rating_row(
            "diagnostic-down",
            0,
            age=2,
            action="downgrades",
            current="Hold",
            previous="Buy",
        ),
        *[
            _rating_row(f"event-{index:03d}", index, age=index)
            for index in range(1, 20)
        ],
    ]
    arguments = _chain(tmp_path, rows=rows)
    candidate = _build(arguments, policy)
    baseline = _diagnostics(candidate, arguments, policy)
    with localcontext() as context:
        context.prec = 6
        changed_context = _diagnostics(candidate, arguments, policy)
    assert changed_context == baseline
    assert changed_context.diagnostics_sha256 == baseline.diagnostics_sha256
    first = next(
        item for item in baseline.rows if item.security_id == "security-000"
    )
    with analyst_decimal_context():
        assert first.directional_breadth == Decimal(1) / Decimal(3)
    assert first.event_diversity == 3


def test_diagnostics_refuse_partial_candidate_evidence(tmp_path, policy):
    arguments = _chain(tmp_path)
    evidence = arguments["evidence"]
    arguments["evidence"] = dataclasses.replace(
        evidence,
        common_events=evidence.common_events[1:],
    )
    candidate = _build(arguments, policy)
    assert candidate.refusals
    with pytest.raises(StockSignalError, match="unavailable for a refusing"):
        _diagnostics(candidate, arguments, policy)


# --- Independent review regressions (Claude, 2026-08-29) --------------------
# Each pins a property the implementation already satisfies but that survived
# a reverse mutation of its guard, so a later refactor could silently drop it.


def test_decay_has_no_hard_cutoff_beyond_the_pinned_short_horizon(policy):
    """Pin the whole frozen history span, not only age 120.

    ``rating_decay_weight`` promises it "never truncates old or
    tiny-but-nonzero contributions", and the frozen 2013-2026 history is
    roughly 3,400 sessions. The existing no-cutoff regression stops at age
    120, so a truncation introduced anywhere beyond that would silently drop
    the oldest events from every raw sum while every test stayed green.
    """
    from decimal import Context, ROUND_HALF_EVEN

    wide = Context(prec=60, rounding=ROUND_HALF_EVEN)
    previous = rating_decay_weight(120, policy=policy)
    for age in (251, 400, 1000, 2000, 3400):
        weight = rating_decay_weight(age, policy=policy)
        assert weight > 0, f"age {age} truncated to a hard zero"
        assert weight < previous, f"decay is not strictly decreasing at {age}"
        expected = wide.power(
            Decimal("0.5"), wide.divide(Decimal(age), Decimal(20))
        )
        assert abs(weight - expected) < Decimal("1e-40"), (age, weight, expected)
        previous = weight


def test_non_exempt_identity_refusal_still_blocks_the_cross_section(
    tmp_path, policy
):
    """Only the four proven-ineligible reasons may be exempted.

    ``PROVEN_INELIGIBLE_IDENTITY_REFUSAL_REASONS`` is pinned as a constant,
    but nothing exercised an identity-stage refusal outside that set, so the
    filter could stop consulting it and stay green. An unmapped ticker means
    the issuer is unknown, not proven ineligible, and must keep blocking.
    """
    rows = [
        *[_rating_row(f"event-{index:03d}", index, age=index) for index in range(20)],
        _rating_row("event-unmapped", 999, age=0),
    ]
    arguments = _chain(tmp_path, rows=rows)
    identity_refusals = [
        item
        for item in arguments["upstream"].refusals
        if item.stage.value == "identity"
    ]
    assert identity_refusals, "fixture must produce an identity-stage refusal"
    assert all(
        item.reason not in PROVEN_INELIGIBLE_IDENTITY_REFUSAL_REASONS
        for item in identity_refusals
    ), "this regression requires a refusal outside the exempt set"
    candidate = _build(arguments, policy)
    assert not candidate.scores
    assert not candidate.pdf_formula_available
    assert StockScoreRefusalReason.UPSTREAM_IDENTITY_OR_ONTOLOGY_REFUSAL in {
        item.reason for item in candidate.refusals
    }


def test_frozen_candidate_contract_rejects_weakened_records(tmp_path, policy):
    """The record-level guards are the last line if a builder path regresses.

    The builder clears partial output itself, so the frozen dataclass checks
    are only reachable by direct construction - which is exactly how a later
    consumer or fixture would assemble one.
    """
    scoring = _build(_chain(tmp_path / "scoring"), policy)
    assert scoring.pdf_formula_available and not scoring.refusals
    with pytest.raises(StockSignalError, match="production authority"):
        dataclasses.replace(scoring, authority="production-authority")
    with pytest.raises(StockSignalError, match="residualization"):
        dataclasses.replace(scoring, residualization_state="ready")
    assert scoring.residualization_state == RESIDUALIZATION_BLOCK
    assert scoring.authority == STRUCTURAL_ONLY_AUTHORITY
    assert scoring.final_executable_available is False

    refusing_rows = [
        *[_rating_row(f"event-{index:03d}", index, age=index) for index in range(20)],
        _rating_row("event-unmapped", 999, age=0),
    ]
    refusing = _build(_chain(tmp_path / "refusing", rows=refusing_rows), policy)
    assert refusing.refusals and not refusing.scores
    with pytest.raises(StockSignalError, match="partial score artifact"):
        dataclasses.replace(refusing, scores=scoring.scores)
